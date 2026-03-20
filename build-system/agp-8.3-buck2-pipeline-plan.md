# AGP 8.3 deep-dive: APK/AAB pipeline, model extraction, and Buck2 offload plan

This document maps the Android Gradle Plugin (AGP) build pipeline in this repository and gives an implementation plan to:

1. extract full build model data,
2. bypass Java/Kotlin compilation + dexing in AGP,
3. run those steps in Buck2,
4. feed generated JAR/DEX artifacts back into AGP for final APK/AAB packaging.

> Scope: this is aligned to AGP 8.3-era task wiring in `build-system/gradle-core`.

---

## 1) AGP task-flow for APK and AAB (what AGP does today)

## 1.1 Java/Kotlin compile registration and class publication

AGP registers Java compilation via `createJavacTask()`, which first wires `JavaPreCompileTask` (annotation processor discovery metadata), then `JavaCompileCreationAction`, and finally publishes compiled classes into `ScopedArtifact.CLASSES` via `InternalArtifactType.JAVAC`. Kotlin compilation is handled by Kotlin Gradle plugin tasks, but AGP still consumes classes through scoped artifacts and task dependencies. `PackageApplication` explicitly depends on `taskContainer.javacTask` for non-KMP components.  

Key source points:
- `TaskManager.createJavacTask()` and `postJavacCreation()`.  
- `JavaCompileCreationAction` registers `JAVAC` output + AP-generated sources.  
- `TaskManager.createPackagingTask()` adds `dependsOn(taskContainer.javacTask)`.  

## 1.2 Dex pipeline

For non-minified variants, AGP creates dex pipeline using:
- `DexArchiveBuilderTask` (class -> dex archives),
- optional `DexFileDependenciesTask` (file deps dexing when desugar transform path is used),
- `DexMergingTask` in several modes (`MERGE_ALL`, `MERGE_EXTERNAL_LIBS`, etc.) based on mono/legacy/native multidex.

For minified variants (`minifiedEnabled`), AGP routes through code shrinker and returns early because shrinker (R8) performs dexing.  

Key source points:
- `TaskManager.createPostCompilationTasks()`: minified branch early-return.
- `TaskManager.createDexTasks()`.
- `TaskManager.createDexMergingTasks()`.

## 1.3 APK packaging flow

`createPackagingTask()` registers `PackageApplication`, wiring assets/resources/manifest + compiled code dependencies, then binds `assemble` to produced `SingleArtifact.APK`. This is the point where provided DEX/JAR inputs must be visible to AGP artifacts so final APK packaging can proceed unchanged.  

## 1.4 AAB packaging flow

For application variants, AGP registers bundle path in `ApplicationTaskManager.createDynamicBundleTask()`:
- `PerModuleBundleTask`
- `PackageBundleTask`
- `FinalizeBundleTask`
plus bundle model/listing and extraction helpers.

So, if you replace compile/dex outputs while preserving artifacts consumed by these tasks, AAB flow remains AGP-driven.

---

## 2) Build-model extraction (full dependency/model data)

AGP exposes v2 tooling models through parameterized `ModelBuilder` (`org.gradle.tooling.provider.model.ParameterizedToolingModelBuilder`) and supports:
- `BasicAndroidProject`
- `AndroidProject`
- `VariantDependencies`
- `VariantDependenciesAdjacencyList`
- etc.

`VariantDependencies` requires parameterized query (`ModelBuilderParameter`) and provides compile/runtime dependency graphs via `ArtifactDependencies`.

### 2.1 Why parameterized model matters

`ModelBuilder.buildAll(className, parameter, project)` is mandatory for `VariantDependencies*`; non-parameterized query throws. Parameter has `variantName` and runtime-classpath toggles (`dontBuildRuntimeClasspath`, etc.).

### 2.2 Init-script to inject and extract “full build model” inputs

Gradle init scripts cannot directly run Tooling API against the same daemon process the way an external client does, but they can:
- inject model-related properties globally,
- register introspection tasks that serialize per-variant compile/runtime classpaths and AP paths,
- emit enough data to reconstruct Buck2 compile graph.

Use this init script as `init-agp83-model.gradle`:

```groovy
// init-agp83-model.gradle
import groovy.json.JsonOutput

// Global model-oriented property injection.
gradle.beforeProject { p ->
    p.extensions.extraProperties.set("android.injected.build.model.v2", "true")
    // v1 compatibility knobs if needed by mixed tooling:
    p.extensions.extraProperties.set("android.injected.build.model.only.versioned", "4")
    p.extensions.extraProperties.set("android.injected.build.model.feature.full.dependencies", "true")
}

gradle.projectsEvaluated {
    allprojects { proj ->
        proj.tasks.register("dumpAgpBuck2Model") {
            group = "verification"
            description = "Dump AGP variant classpaths/inputs for Buck2 handoff"
            doLast {
                def rootOut = new File(gradle.startParameter.projectCacheDir ?: new File(rootProject.buildDir, "agp-buck2-model").absolutePath)
                rootOut.mkdirs()

                def rows = []

                proj.configurations.findAll { it.canBeResolved }.each { cfg ->
                    def lower = cfg.name.toLowerCase(Locale.ROOT)
                    if (lower.contains("compileclasspath") ||
                        lower.contains("runtimeclasspath") ||
                        lower.contains("annotationprocessor")) {
                        rows << [
                            project: proj.path,
                            configuration: cfg.name,
                            files: cfg.files.collect { it.absolutePath }.sort()
                        ]
                    }
                }

                def out = new File(rootOut, "${proj.path.replace(':','_')}-agp-buck2-model.json")
                out.text = JsonOutput.prettyPrint(JsonOutput.toJson(rows))
                println "Wrote ${out.absolutePath}"
            }
        }
    }
}
```

Run:

```bash
./gradlew -I init-agp83-model.gradle :app:dumpAgpBuck2Model
```

For **full structured variant dependency graph**, use an external Tooling API client (or IDE sync bridge) to query:
- `com.android.builder.model.v2.models.AndroidProject`
- `com.android.builder.model.v2.models.VariantDependencies` (parameterized per variant)

with `ModelBuilderParameter.variantName` and runtime toggles.

---

## 3) Plan to “nuke” AGP Java/Kotlin compile + dex and replace with Buck2 outputs

## 3.1 Design constraints

- If minification is enabled, AGP’s shrinker path owns dexing; offload strategy differs.
- Packaging/bundle tasks must still receive expected artifacts (`ScopedArtifact.CLASSES` and/or dex artifacts) without breaking AGP task graph.
- AGP task dependencies (e.g., `PackageApplication` -> `javacTask`) may require no-op replacement tasks or artifact substitution rather than hard task deletion.

## 3.2 Recommended integration mechanism

Use Android Components + Scoped Artifacts API in module build scripts (or convention plugin) to **replace** classes and dex artifact inputs with Buck2-produced files:

1. Register a custom task `buck2Compile<Variant>`:
   - consumes source list + compile classpath + processor path metadata,
   - invokes Buck2 target producing a deterministic classes JAR.

2. Publish this JAR into AGP class stream by replacing/project-scoping `ScopedArtifact.CLASSES` content (or transform to expected directory form).

3. Register `buck2Dex<Variant>` that converts jar -> dex (D8/R8 in Buck2 action) and produces dex directories/files.

4. Wire AGP artifact replacement for dex merge/package input artifact(s) so `PackageApplication` / bundle tasks consume Buck2 dex outputs.

5. Replace AGP compile/dex tasks with no-op or disable execution:
   - keep graph nodes if downstream `dependsOn` is hard-coded,
   - but reroute produced artifacts to Buck2 outputs.

## 3.3 Practical disablement strategy

- Java compile: set `JavaCompile` tasks to `enabled = false` **only after** ensuring alternative artifact is provided and no hard runtime dependency requires actual execution.
- Kotlin compile: similarly for `KotlinCompile` tasks.
- Dex tasks: disable `DexArchiveBuilderTask` and `DexMergingTask` only when all consuming artifacts are replaced.

Safer first phase: keep AGP tasks enabled but make them up-to-date/no-op by pointing sources empty and feeding prebuilt outputs; then tighten to true disablement once stable.

---

## 4) Buck2-driven compilation from AGP model

## 4.1 Data to export from AGP model/configurations

Per variant, export:
- source roots (java + kotlin + generated),
- bootclasspath (`android.jar` etc.),
- compile classpath jars,
- annotation processor path and explicit processor class names/options,
- Javac source/target compatibility,
- Kotlin compiler flags, plugin classpath/options,
- desugar requirements and minSdk.

AGP-side references:
- `JavaCompile.configureProperties()` sets classpath/bootclasspath/toolchain.
- `configureAnnotationProcessorPath()` builds AP path from project + external artifacts.
- `JavaPreCompileTask`/AP metadata helps detect processors.

## 4.2 Buck2 target layout

Recommended split per variant:
- `:<variant>_javakotlin_jar` — runs javac/kotlinc + AP/KSP/KAPT workflow, emits classes JAR.
- `:<variant>_dex` — consumes classes JAR (+ needed classpath for desugar), emits dex output.
- Optional: `:<variant>_proguarded_dex` when release/minified path is moved out too.

## 4.3 Javac/Kotlin execution environment

1. JDK/toolchain:
   - Match AGP/Gradle toolchain version (Java toolchain configured in project).
2. Bootclasspath:
   - include android platform jar(s) matching compileSdk.
3. Compile classpath:
   - all jars/aars-derived jars from AGP compile classpath export.
4. Annotation processing:
   - AP path from AGP annotation processor configuration.
   - options (`-Akey=value`) mirrored from AGP DSL and generated providers.
5. Kotlin:
   - mirror freeCompilerArgs, language/api versions, plugin classpath/options, KAPT stubs if used.
6. Generated sources/resources:
   - ensure AP/KSP outputs are fed into downstream compile steps and packaged classes jar.

## 4.4 Getting compile classpath into Buck2 executor

- Generate a machine-readable lock/manifest file per variant from AGP (JSON from init-task above).
- Normalize file paths + hash content to improve remote caching.
- In Buck2 rule implementation, pass classpath as param-file to avoid command-line length limits.
- Separate “direct” and “transitive” classpath if using strict deps mode.

---

## 5) Re-inject Buck2 outputs into AGP final APK/AAB build

## 5.1 Jar path

- Buck2 emits classes jar.
- AGP consumes it as replacement project classes artifact (scoped classes stream).
- Keep resource/manifest tasks untouched.

## 5.2 Dex path

- Buck2 emits dex files/dirs in AGP-compatible layout.
- Replace dex merging inputs/artifacts so `PackageApplication` (APK) and `PerModuleBundleTask`/`PackageBundleTask` (AAB) can proceed unchanged.

## 5.3 Validation checkpoints

Per variant:
1. `assemble<Variant>` succeeds with AGP compile/dex tasks disabled.
2. produced APK/AAB installs/runs.
3. class/resource symbol parity against baseline AGP build.
4. reproducibility hash check on jar and dex outputs.

---

## 6) Suggested phased rollout

1. **Observe-only phase**
   - Keep AGP pipeline intact, export model/classpath data, run Buck2 in parallel, compare jars/dex.
2. **Jar substitution phase**
   - Replace compiled classes with Buck2 jar; keep AGP dexing.
3. **Dex substitution phase**
   - Replace AGP dexing outputs with Buck2 dex.
4. **Hard disable phase**
   - disable Java/Kotlin compile + dex tasks, retain packaging/bundle tasks.
5. **Release/minify alignment**
   - integrate R8/desugar parity for release builds.

---

## 7) Command cookbook

```bash
# 1) Dump AGP/Buck2 handoff model (classpath-oriented)
./gradlew -I init-agp83-model.gradle :app:dumpAgpBuck2Model

# 2) Build normal AGP APK (baseline)
./gradlew :app:assembleDebug

# 3) Build normal AGP AAB (baseline)
./gradlew :app:bundleRelease

# 4) (After integration) run AGP packaging with Buck2 compile/dex replaced
./gradlew :app:assembleDebug :app:bundleRelease
```

---

## 8) Source map used for this plan

- Task graph wiring: `TaskManager.kt`, `ApplicationTaskManager.kt`.
- Java compile/AP wiring: `JavaCompile.kt`, `JavaCompileUtils.kt`.
- Tooling model entrypoints/parameterized dependency model: `ModelBuilder.kt`, `ModelBuilderParameter.kt`, `VariantDependencies.kt`, `ArtifactDependencies.kt`.
- Injected property constants (v2 + IDE properties): `InjectedProperties.kt`, and v1 compatibility flags in `AndroidProject.java`.
