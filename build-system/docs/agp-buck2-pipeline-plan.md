# AGP build pipeline deep dive + Buck2 interception plan

This repository checkout is **APK-task-chain centric** (`Dex` -> `PackageApplication` -> optional `ZipAlign`) and, in this branch snapshot, there is no first-class App Bundle (`.aab`) task pipeline implementation.

## 1) Where AGP creates the model and task graph

- The Android tooling model builder is `ModelBuilder` (`ToolingModelBuilder`) and returns `AndroidProject` from `buildAll`.
- `BasePlugin` constructs and registers `ModelBuilder` in `createExtension()`.
- Variant task graph creation flows from `ApplicationTaskManager#createTasksForVariantData`, which calls post-compilation and packaging creation.

## 2) APK pipeline in this branch (high-level)

Per variant, the dominant flow is:

1. Java compile task (`compile<Variant>JavaWithJavac`) configured via `JavaCompileConfigAction`.
2. Post-compile pipeline in `TaskManager#createPostCompilationTasks`:
   - optional ProGuard,
   - optional PreDex,
   - optional main-dex list tasks for legacy multidex,
   - `Dex` task created and wired to class/library generators.
3. Final packaging in `TaskManager#createPackagingTask`:
   - `PackageApplication` task consumes dex output + resources + merged java resources,
   - optional `ZipAlign` for signed variants,
   - output assemble task depends on package/zipalign tasks.

## 3) AAB status for this repo (and how to verify branch expectations)

- In this checkout, no modern app-bundle task chain (`bundle<Variant>`, `PackageBundleTask`, `BundleTool` integration) is present in AGP task wiring.
- This is a statement about the **current sources checked out**, not about your whole codebase history or all branches.
- If you suspect the wrong branch/revision, validate quickly by searching task orchestration sources for bundle task creation and comparing with your intended branch.
- Any AAB strategy in this doc is therefore architectural guidance for newer AGP lines, not directly runnable from this tree snapshot.

## 4) Init script to dump full build model

Use:

```bash
./gradlew -I build-system/docs/init-scripts/dump-agp-model.init.gradle dumpAgpBuildModel \
  -PagpModelOutDir=$PWD/build/agp-model
```

What it does:

- Finds Android subprojects by detecting `BasePlugin`.
- Reflects `BasePlugin` internals (`androidBuilder`, `variantManager`, `taskManager`, etc.).
- Instantiates `ModelBuilder` and calls `buildAll("com.android.builder.model.AndroidProject", project)`.
- Writes:
  - `*.AndroidProject.bin` (Java-serialized full model object graph),
  - `*.summary.json` (quick-readable projection per variant),
  - `index.json` (artifact index).

## 5) Plan: replace Java/Kotlin compile + dex with Buck2 outputs

This codebase already demonstrates supported mutation points:

- Override dex inputs from a custom jar task (`variant.dex.inputFiles = ...`).
- Clear dex libraries (`variant.dex.libraries = []`) when supplying preprocessed bytecode.

### Step-by-step interception plan

1. **Extract model and lock coordinates**
   - Run `dumpAgpBuildModel` and pick target variant(s).
   - Record `mainArtifact.compileTaskName`, `assembleTaskName`, generated source folders, and dependency tree.

2. **Build Buck2 compile classpath manifest**
   - From `mainArtifact.dependencies` recursively collect:
     - Java libraries (`JavaLibrary#getJarFile` + nested deps),
     - Android library jars (`AndroidLibrary#getJarFile`, plus `getLocalJars`).
   - Add bootclasspath from `AndroidProject#getBootClasspath`.
   - Add generated source/resource roots from artifact metadata.

3. **Mirror AGP preprocessing before javac/kotlinc in Buck2**
   - Generate sources required by annotation processors / data binding / AIDL / BuildConfig / R classes by running AGP source-gen tasks first (use `mainArtifact.ideSetupTaskNames` and source-gen task names).
   - Capture processor path/options from Gradle task configuration (or from model + convention in build scripts).
   - Build per-language Buck2 rules:
     - Java compile target producing classes jar,
     - Kotlin compile target producing classes dir/jar,
     - merge into one deterministic classes jar.

4. **Dex in Buck2**
   - Separate Buck2 target runs D8/dx over compiled jar(s) and required libs, producing dex archive/folder in AGP-compatible layout.

5. **Inject outputs back into AGP and skip native compile/dex path**
   - In module build script or injected script:
     - Disable or no-op `variant.javaCompile` / `variant.javaCompiler` where safe.
     - Force dex task to consume Buck2-produced jar/dex:
       - if feeding bytecode into AGP dex: set `variant.dex.inputFiles` to Buck2 jar(s),
       - if feeding ready dex directly: wire packaging task inputs to Buck2 dex folder and make AGP dex task a no-op/disabled.
     - Remove AGP dex library inputs when Buck2 already merged dependencies (`variant.dex.libraries = []`).

6. **Keep AGP packaging/signing/resources intact**
   - Keep `PackageApplication` (+ `ZipAlign`) unchanged so AGP still handles manifests/resources/assets/signing/publishing.

7. **Validation loop**
   - Compare APK contents/classes against baseline.
   - Verify multidex main-dex list behavior (legacy mode) when Buck2 dex is substituted.
   - Run instrumentation/unit tests for impacted variants.

## 6) Buck2 environment preparation details

For each variant, construct a reproducible compile invocation contract:

- **Inputs**
  - Java/Kotlin source roots (including generated sources).
  - Compile classpath jars from model dependency graph.
  - Bootclasspath (`android.jar` set from model bootClasspath).
  - Annotation processor classpath + processor options.

- **Compiler settings**
  - Java source/target compatibility + encoding (mirror `compileOptions` + `JavaCompileConfigAction` behavior).
  - Kotlin JVM target + free compiler args matching Gradle configuration.

- **Outputs**
  - classes directory and normalized classes jar.
  - generated stubs/sources from processors for incremental rebuild determinism.

- **Dex settings**
  - multidex flag + main-dex list (if legacy multidex),
  - optimization/debug flags aligned with AGP variant type.

## 7) Practical integration milestones

1. Read-only phase: dump model, do not alter AGP tasks.
2. Compile offload phase: Buck2 compiles jars; AGP still dexes.
3. Dex offload phase: Buck2 compiles + dexes; AGP only packages/signs.
4. Hardening phase: cache keys, deterministic archives, parity tests.

## 8) Notes for modern AGP/AAB users

If you run this strategy against modern AGP (outside this repo), map the same concept to bundle tasks:

- preserve resource processing + manifest + signing + bundle packaging tasks,
- substitute JVM compile + dex/art profile inputs from Buck2,
- keep variant-aware artifact wiring through the Android Components API.
