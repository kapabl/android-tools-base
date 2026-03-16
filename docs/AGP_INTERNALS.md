# How AGP Works (8.3)

APK/AAB build flow, task orchestration, compilation, dexing, packaging.

---

## 1. Build Pipeline

### Task Flow

```
┌──────────────┐
│  PreBuild    │
└──────┬───────┘
       │
┌──────▼────────┐
│  Source Gen   │ (AIDL, RenderScript, BuildConfig, R.java)
└──────┬────────┘
       │
┌──────▼────────┐
│  Java/Kotlin  │
│  Compilation  │
└──────┬────────┘
       │
┌──────▼────────┐
│    Dexing     │ (Class → DEX)
└──────┬────────┘
       │
┌──────▼────────┐
│   Resources   │ (AAPT2: compile → link)
└──────┬────────┘
       │
┌──────▼────────┐
│   Packaging   │ (Merge: DEX + resources + libs)
└──────┬────────┘
       │
┌──────▼────────┐
│   Signing     │
└──────┬────────┘
       │
┌──────▼────────┐
│   Assemble    │ → APK/AAB
└───────────────┘
```

### Task Managers

**VariantTaskManager.kt:105**
```kotlin
fun createTasks() {
    for (variant in variants) createTasksForVariant(variant)
}
```

**ApplicationTaskManager.kt:77**
```kotlin
override fun doCreateTasksForVariant() {
    createCommonTasks()
    createBundleTask()  // AAB
    createValidateSigningTask()
}
```

---

## 2. Java/Kotlin Compilation

### 2.1 Compilation Order (Mixed Java/Kotlin)

**CRITICAL:** KAPT → Kotlin → Java

```
KAPT (if present)
  ↓ generates sources
KotlinCompile (.kt → .class)
  ↓ kotlin classes available
JavaCompile (.java → .class)  // can reference Kotlin classes
```

**Tasks:**
- `kapt<Variant>` → `compile<Variant>Kotlin` → `compile<Variant>JavaWithJavac`

**Why:** Kotlin compiler compiles **both** `.kt` and `.java` files together. Pure Java-only code runs after (if needed).

**Files:**
- Kotlin: Kotlin Gradle Plugin (external)
- Java: `JavaCompile.kt:56`

### 2.2 KAPT (Kotlin Annotation Processing)

Bridges Kotlin to Java annotation processors (Room, Dagger).

**Example:**
```kotlin
@Entity data class User(@PrimaryKey val id: Int, val name: String)
@Dao interface UserDao { @Query("SELECT * FROM user") fun getAll(): List<User> }
```

**Flow:**
1. Kotlin → Java stubs (`build/tmp/kapt3/stubs/`)
2. Room processor → `UserDao_Impl.java` (`build/generated/source/kapt/`)
3. Kotlin compiles original + generated

**Config:**
```kotlin
plugins { id("kotlin-kapt") }
dependencies { kapt("androidx.room:room-compiler:2.5.0") }
```

### 2.2.1 AIDL Processing

IPC (Inter-Process Communication) interface generation.

**Input:** `.aidl` files
```java
interface IMyService { String getData(); }
```

**Output:** `build/generated/source/aidl/<variant>/IMyService.java`
```java
public interface IMyService extends android.os.IInterface {
    String getData() throws android.os.RemoteException;
    public static abstract class Stub extends android.os.Binder { ... }
}
```

**Buck2:** Run `aidl` compiler BEFORE javac

### 2.3 JavaCompile Task

**JavaCompile.kt:56**
```kotlin
class JavaCompileCreationAction {
    override val name = "compile${variant}JavaWithJavac"

    outputs:
        - JAVAC → build/intermediates/javac/<variant>/classes
        - AP_GENERATED_SOURCES → build/generated/ap_generated_sources/<variant>
}
```

### 2.4 Classpath Assembly

**ClassesClasspathUtils.kt:28**
```kotlin
class ClassesClasspathUtils {
    val projectClasses: FileCollection
    val subProjectsClasses: FileCollection
    val externalLibraryClasses: FileCollection
}
```

### 2.5 Annotation Processors

**VariantDependencies.kt:89**
```kotlin
val annotationProcessorConfiguration: Configuration?
```

**Output:** `build/intermediates/annotation_processor_list/<variant>/annotationProcessors.json`

---

## 3. Dexing

### 3.1 DexArchiveBuilderTask

**DexArchiveBuilderTask.kt:73** - Converts .class → DEX archives

```kotlin
inputs: projectClasses, subProjectClasses, externalLibClasses
outputs:
  - build/intermediates/dex/<variant>/out/project
  - build/intermediates/dex/<variant>/out/sub-project
  - build/intermediates/dex/<variant>/out/external-libs
```

Incremental, parallel bucketed processing, desugaring support.

### 3.2 DexMergingTask

Merges DEX archives → `build/intermediates/dex_merged/<variant>/classes.dex`
Multi-dex: `classes2.dex`, `classes3.dex`, ...

### 3.3 R8Task (Minification)

**R8Task.kt:94** - Shrinking + desugaring + dexing

```
All classes → Shrink → Obfuscate → Optimize → Desugar → DEX
```

**Outputs:**
- `build/intermediates/dex/<variant>/classes.dex`
- `build/outputs/mapping/<variant>/mapping.txt`

---

## 4. Resources

### AAPT2 Pipeline

```
res/ → AAPT2 Compile → Flat Resources → AAPT2 Link → resources.ap_ + R.java
```

**Outputs:**
- `build/intermediates/processed_res/<variant>/out/resources-<variant>.ap_`
- `build/generated/source/r/<variant>/R.java`

---

## 5. Packaging

### PackageApplication Task

**PackageApplication.kt:55**

**Inputs:**
- DEX: `build/intermediates/dex/<variant>/`
- Resources: `build/intermediates/processed_res/<variant>/`
- Native libs: `build/intermediates/merged_native_libs/<variant>/`
- Assets: `build/intermediates/merged_assets/<variant>/`
- Manifest: `build/intermediates/packaged_manifests/<variant>/`

**Output:** `build/outputs/apk/<variant>/app-<variant>.apk`

### AAB Packaging

`PackageBundleTask` → `build/outputs/bundle/<variant>/app-<variant>.aab`

---

## 6. Dependencies

### VariantDependencies.kt:89

```kotlin
class VariantDependencies {
    val compileClasspath: Configuration
    val runtimeClasspath: Configuration
    val annotationProcessorConfiguration: Configuration?
}
```

**Scopes:** PROJECT, ALL, EXTERNAL
**Types:** CLASSES_JAR, AAR, ANDROID_RES, JNI

---

## 7. Artifact Types

**InternalArtifactType.kt**

| Type | Location |
|------|----------|
| `JAVAC` | `intermediates/javac/<variant>/classes` |
| `AP_GENERATED_SOURCES` | `generated/ap_generated_sources/<variant>` |
| `PROJECT_DEX_ARCHIVE` | `intermediates/dex/<variant>/out/project` |
| `PROCESSED_RES` | `intermediates/processed_res/<variant>/out` |

---

## 8. Build Model (Tooling API)

**ModelBuilder.kt:117**

```kotlin
Models: AndroidProject, VariantDependencies, AndroidDsl
```
- All variants (debug, release, custom)
- Build types and product flavors
- Source sets (main, test, androidTest)
- Dependency graphs
- Compiler options
- Min/target SDK versions
- Signing configurations

**VariantDependencies Model includes:**
- Compile classpath JARs (with coordinates)
- Runtime classpath JARs
- Dependency tree (with conflict resolution)
- Artifact metadata (version, scope)

---

## 9. Task Dependency Graph Example

**For `assembleDebug`:**

```
preBuild
  ├─ generateDebugBuildConfig
  ├─ generateDebugResValues
  ├─ processDebugManifest
  └─ compileDebugAidl
       ↓
mergeDebugResources
  └─ processDebugResources (AAPT2 link)
       ↓
compileDebugJavaWithJavac
  ├─ Inputs: src/main/java, generated sources
  └─ Classpath: android.jar + dependencies
       ↓
dexBuilderDebug
  └─ Converts classes → DEX archives
       ↓
mergeDexDebug (or R8Debug if minifyEnabled)
  └─ Merges DEX archives → final DEX
       ↓
packageDebug
  ├─ Inputs: DEX, resources.ap_, libs, assets
  └─ Output: app-debug.apk
       ↓
assembleDebug (lifecycle task)
```

---

## 10. File Locations Summary

### Intermediate Build Artifacts

```
build/
├── generated/
│   ├── source/
│   │   ├── buildConfig/<variant>/        # BuildConfig.java
│   │   └── r/<variant>/                  # R.java
│   └── ap_generated_sources/<variant>/   # Annotation processor outputs
│
├── intermediates/
│   ├── javac/<variant>/classes/          # Compiled Java classes
│   ├── dex/<variant>/out/                # DEX archives
│   ├── processed_res/<variant>/out/      # resources.ap_ (AAPT2)
│   ├── merged_native_libs/<variant>/     # Native .so files
│   ├── merged_assets/<variant>/          # Assets
│   └── packaged_manifests/<variant>/     # AndroidManifest.xml
│
└── outputs/
    ├── apk/<variant>/app-<variant>.apk   # Final APK
    └── bundle/<variant>/app.aab          # Final AAB
```

---

## 11. Key Interfaces and Extension Points

### 11.1 Variant API

**Access variant properties:**
```kotlin
androidComponents {
    onVariants { variant ->
        variant.name              // "debug", "release"
        variant.applicationId     // Package name
        variant.minSdk            // Min SDK version
        variant.artifacts         // Access to artifacts
        variant.sources           // Source sets
    }
}
```

### 11.2 Artifact Transforms API

**Transform classes before dexing:**
```kotlin
androidComponents {
    onVariants { variant ->
        variant.artifacts.use(taskProvider)
            .wiredWith { task.inputClasses }
            .toTransform(ScopedArtifact.CLASSES)
    }
}
```

---

## Summary

The AGP 8.3 build pipeline is highly modular with clear separation:

1. **Task orchestration** via `VariantTaskManager` and subclasses
2. **Compilation** uses standard Gradle `JavaCompile` with AGP-specific configuration
3. **Dexing** is incremental with scope-based processing
4. **Packaging** merges multiple artifact types into final APK/AAB
5. **Build model** exposes all configuration via Tooling API

All tasks are **incremental** and **cacheable** where possible, with fine-grained dependency tracking through Gradle's artifact system.
