# Buck2 Modular Android SDK Architecture

## Table of Contents

1. [Overview](#overview)
2. [Problem Statement](#problem-statement)
3. [Modular SDK Component System](#modular-sdk-component-system)
4. [Custom Starlark Rules](#custom-starlark-rules)
5. [Rule Implementations](#rule-implementations)
6. [Complete Integration with AGP](#complete-integration-with-agp)
7. [genrule vs Starlark vs BXL](#genrule-vs-starlark-vs-bxl)

---

## Overview

This document describes a **modular, hermetic Buck2 build system** for Android that:

1. **Extracts only needed Android SDK components** (no full 30GB SDK required)
2. **Provides clean, declarative user-facing rules**
3. **Implements internals using genrule/Starlark**
4. **Integrates with AGP-extracted build models**

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    User-Facing Buck2 Rules                   │
│  android_dex(classes=[...], deps=[...], d8_version="33.0.0") │
│  android_compile(srcs=[...], deps=[...], javac_version="11") │
│  android_resources(res=[...], aapt2_version="33.0.0")        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ (uses)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Starlark Rule Implementations (.bzl)            │
│  - Resolve SDK components                                    │
│  - Build command arguments                                   │
│  - Execute via ctx.actions.run() or genrule                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ (depends on)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│           Modular Android SDK Components                     │
│  android_sdk_component(name="d8", version="33.0.0")          │
│  android_sdk_component(name="platform_33", ...)              │
│  android_sdk_component(name="aapt2", version="33.0.0")       │
└─────────────────────────────────────────────────────────────┘
```

---

## Problem Statement

### Traditional Approach Problems

**Full Android SDK Installation:**
```
/opt/android-sdk/
├── platforms/              # ~500MB per platform × 10 versions = 5GB
├── build-tools/            # ~100MB per version × 10 versions = 1GB
├── system-images/          # ~1.5GB per image × 5 images = 7.5GB
├── emulator/               # ~500MB
├── platform-tools/         # ~20MB
├── sources/                # ~5GB
└── ndk/                    # ~2GB per version
Total: ~30GB
```

**Problems:**
- ❌ CI/CD machines need full SDK installed
- ❌ Developers need same SDK version
- ❌ Non-hermetic builds (relies on $ANDROID_SDK_ROOT)
- ❌ Slow CI setup (downloading/extracting 30GB)
- ❌ Version drift between machines

### Our Solution: Modular SDK Components

**Extract only what you need:**
```
buck2-android-sdk/
├── d8-33.0.0               # ~5MB (just the dexer)
├── platform-android-33     # ~70MB (just android.jar)
├── aapt2-33.0.0            # ~8MB (just resource compiler)
├── zipalign-33.0.0         # ~50KB
└── apksigner-33.0.0        # ~2MB
Total for typical build: ~85MB
```

**Benefits:**
- ✅ Hermetic builds (explicit SDK component dependencies)
- ✅ Fast CI/CD (download only what's needed)
- ✅ Remote caching (Buck2 caches SDK components)
- ✅ Version pinning (each target specifies exact versions)
- ✅ Parallel downloads (Buck2 fetches components in parallel)

---

## Modular SDK Component System

### Base SDK Component Rule

**File:** `android-sdk/sdk_component.bzl`

```python
"""
Modular Android SDK component extraction.

Downloads and extracts specific Android SDK components from Google's repository.
"""

def android_sdk_component(
    name,
    component_type,
    version,
    sha256 = None,
    visibility = ["PUBLIC"]):
    """
    Extracts a specific Android SDK component.

    Args:
        name: Target name
        component_type: Type of component (d8, platform, aapt2, etc.)
        version: Component version
        sha256: Optional SHA-256 checksum for verification
        visibility: Target visibility

    Example:
        android_sdk_component(
            name = "d8_33",
            component_type = "d8",
            version = "33.0.0",
        )
    """

    # Component type to URL mapping
    component_urls = {
        "d8": "https://dl.google.com/android/repository/build-tools_r{version}-linux.zip",
        "platform": "https://dl.google.com/android/repository/platform-{api_level}_r{revision}.zip",
        "aapt2": "https://dl.google.com/android/repository/build-tools_r{version}-linux.zip",
        "zipalign": "https://dl.google.com/android/repository/build-tools_r{version}-linux.zip",
        "apksigner": "https://dl.google.com/android/repository/build-tools_r{version}-linux.zip",
        "emulator": "https://dl.google.com/android/repository/emulator-linux_x64-{version}.zip",
        "system-image": "https://dl.google.com/android/repository/sys-img/google_apis/x86_64-{api_level}_r{revision}.zip",
    }

    url_template = component_urls.get(component_type)
    if not url_template:
        fail("Unknown component type: {}".format(component_type))

    url = url_template.format(version = version, api_level = version.split(".")[0], revision = version.split(".")[-1])

    # Use http_archive to download and extract
    native.http_archive(
        name = name,
        url = url,
        sha256 = sha256,
        build_file_content = _generate_build_file(component_type, version),
    )

def _generate_build_file(component_type, version):
    """Generate BUILD file for extracted SDK component."""

    if component_type == "d8":
        return """
filegroup(
    name = "d8_binary",
    srcs = ["android-{}/d8"],
    visibility = ["PUBLIC"],
)

filegroup(
    name = "d8_jar",
    srcs = ["android-{}/lib/d8.jar"],
    visibility = ["PUBLIC"],
)
""".format(version, version)

    elif component_type == "platform":
        return """
filegroup(
    name = "android_jar",
    srcs = ["android.jar"],
    visibility = ["PUBLIC"],
)

filegroup(
    name = "framework_aidl",
    srcs = ["framework.aidl"],
    visibility = ["PUBLIC"],
)
"""

    elif component_type == "aapt2":
        return """
filegroup(
    name = "aapt2_binary",
    srcs = ["android-{}/aapt2"],
    visibility = ["PUBLIC"],
)
""".format(version)

    elif component_type == "zipalign":
        return """
filegroup(
    name = "zipalign_binary",
    srcs = ["android-{}/zipalign"],
    visibility = ["PUBLIC"],
)
""".format(version)

    elif component_type == "apksigner":
        return """
filegroup(
    name = "apksigner_jar",
    srcs = ["android-{}/lib/apksigner.jar"],
    visibility = ["PUBLIC"],
)
""".format(version)

    else:
        return 'filegroup(name = "files", srcs = glob(["**/*"]), visibility = ["PUBLIC"])'
```

### SDK Component Registry

**File:** `android-sdk/BUCK`

```python
load(":sdk_component.bzl", "android_sdk_component")

# Build Tools 33.0.0
android_sdk_component(
    name = "d8_33_0_0",
    component_type = "d8",
    version = "33.0.0",
    sha256 = "...", # Add actual SHA-256
)

android_sdk_component(
    name = "aapt2_33_0_0",
    component_type = "aapt2",
    version = "33.0.0",
    sha256 = "...",
)

android_sdk_component(
    name = "zipalign_33_0_0",
    component_type = "zipalign",
    version = "33.0.0",
    sha256 = "...",
)

android_sdk_component(
    name = "apksigner_33_0_0",
    component_type = "apksigner",
    version = "33.0.0",
    sha256 = "...",
)

# Platform 33 (Android 13)
android_sdk_component(
    name = "platform_33",
    component_type = "platform",
    version = "33.3",
    sha256 = "...",
)

# Platform 34 (Android 14)
android_sdk_component(
    name = "platform_34",
    component_type = "platform",
    version = "34.2",
    sha256 = "...",
)

# Emulator
android_sdk_component(
    name = "emulator_latest",
    component_type = "emulator",
    version = "33.1.10",
    sha256 = "...",
)

# System Images
android_sdk_component(
    name = "system_image_x86_64_api33",
    component_type = "system-image",
    version = "33.12",
    sha256 = "...",
)
```

---

## Custom Starlark Rules

### android_dex Rule

**File:** `android-rules/android_dex.bzl`

```python
"""
Android DEX conversion rule.

Converts Java/Kotlin bytecode (JARs) to Android DEX format using D8.
"""

def _android_dex_impl(ctx):
    """
    Implementation of android_dex rule.

    Runs D8 dexer on compiled classes and dependencies.
    """

    # Collect all JARs to dex
    all_jars = []

    # Add compiled classes
    for classes_target in ctx.attrs.classes:
        all_jars.extend(classes_target[DefaultInfo].default_outputs)

    # Add dependency JARs
    for dep in ctx.attrs.deps:
        all_jars.extend(dep[DefaultInfo].default_outputs)

    # Get D8 tool from SDK component
    d8_version = ctx.attrs.d8_version
    d8_target = "//android-sdk:d8_{}".format(d8_version.replace(".", "_"))
    d8_binary = ctx.attrs._d8_tool[RunInfo]

    # Get android.jar (platform API) from SDK component
    platform_version = ctx.attrs.platform_version
    platform_target = "//android-sdk:platform_{}".format(platform_version)
    android_jar = ctx.attrs._platform_jar[DefaultInfo].default_outputs[0]

    # Declare output directory
    output_dir = ctx.actions.declare_directory("dex")

    # Build D8 command
    cmd = cmd_args()
    cmd.add(d8_binary)
    cmd.add("--lib", android_jar)
    cmd.add("--min-api", str(ctx.attrs.min_sdk))

    # Debug vs release mode
    if ctx.attrs.debug:
        cmd.add("--debug")
    else:
        cmd.add("--release")

    # Multi-dex support
    if ctx.attrs.multi_dex:
        if ctx.attrs.main_dex_list:
            main_dex_file = ctx.attrs.main_dex_list[DefaultInfo].default_outputs[0]
            cmd.add("--main-dex-list", main_dex_file)
        cmd.add("--main-dex-rules", ctx.attrs.main_dex_rules_file) if ctx.attrs.main_dex_rules_file else None

    # Desugaring
    if ctx.attrs.enable_desugaring:
        cmd.add("--desugaring")

    # Output directory
    cmd.add("--output", output_dir.as_output())

    # Input JARs
    for jar in all_jars:
        cmd.add(jar)

    # Run D8
    ctx.actions.run(
        cmd,
        category = "android_dex",
        identifier = ctx.attrs.name,
    )

    return [
        DefaultInfo(default_output = output_dir),
        DexInfo(
            dex_files = output_dir,
            min_sdk = ctx.attrs.min_sdk,
            multi_dex = ctx.attrs.multi_dex,
        ),
    ]

android_dex = rule(
    impl = _android_dex_impl,
    attrs = {
        # User-facing attributes
        "classes": attrs.list(attrs.dep(), default = [], doc = "Compiled classes to dex"),
        "deps": attrs.list(attrs.dep(), default = [], doc = "Dependency JARs to include in dex"),

        # SDK component versions
        "d8_version": attrs.string(default = "33.0.0", doc = "D8 version to use"),
        "platform_version": attrs.string(default = "33", doc = "Android platform version"),

        # DEX options
        "min_sdk": attrs.int(mandatory = True, doc = "Minimum Android API level"),
        "multi_dex": attrs.bool(default = False, doc = "Enable multi-dex"),
        "main_dex_list": attrs.option(attrs.dep(), default = None, doc = "Main dex list file"),
        "main_dex_rules_file": attrs.option(attrs.source(), default = None, doc = "ProGuard rules for main dex"),
        "debug": attrs.bool(default = False, doc = "Build in debug mode"),
        "enable_desugaring": attrs.bool(default = True, doc = "Enable Java 8+ desugaring"),

        # Private attributes - resolved SDK components
        "_d8_tool": attrs.exec_dep(
            default = "//android-sdk:d8_{d8_version}".format(d8_version = "33_0_0"),
            doc = "D8 dexer tool",
        ),
        "_platform_jar": attrs.dep(
            default = "//android-sdk:platform_{platform_version}".format(platform_version = "33"),
            doc = "Android platform JAR (android.jar)",
        ),
    },
    doc = "Converts Java/Kotlin bytecode to Android DEX format",
)
```

### Provider for DEX Info

```python
DexInfo = provider(
    fields = {
        "dex_files": provider_field(typing.Any, default = None),
        "min_sdk": provider_field(typing.Any, default = None),
        "multi_dex": provider_field(typing.Any, default = None),
    },
    doc = "Information about DEX outputs",
)
```

---

## android_compile Rule

**File:** `android-rules/android_compile.bzl`

```python
"""
Android Java/Kotlin compilation rule.

Compiles Java and Kotlin sources with Android-specific configuration.
"""

def _android_compile_impl(ctx):
    """
    Implementation of android_compile rule.

    Compiles Java/Kotlin sources with annotation processors.
    """

    # Collect source files
    java_srcs = []
    kotlin_srcs = []

    for src in ctx.attrs.srcs:
        if src.extension == ".java":
            java_srcs.append(src)
        elif src.extension == ".kt":
            kotlin_srcs.append(src)

    # Collect classpath
    classpath = []
    for dep in ctx.attrs.deps:
        classpath.extend(dep[JavaInfo].compile_classpath) if JavaInfo in dep else None

    # Get Android SDK components
    android_jar = ctx.attrs._android_jar[DefaultInfo].default_outputs[0]
    classpath.append(android_jar)

    # Declare output JAR
    output_jar = ctx.actions.declare_output("{}.jar".format(ctx.attrs.name))

    # Compile Java sources
    if java_srcs:
        _compile_java(
            ctx,
            srcs = java_srcs,
            classpath = classpath,
            output = output_jar,
            annotation_processors = ctx.attrs.annotation_processors,
            annotation_processor_deps = ctx.attrs.annotation_processor_deps,
            annotation_processor_params = ctx.attrs.annotation_processor_params,
            source_level = ctx.attrs.source_level,
            target_level = ctx.attrs.target_level,
        )

    # Compile Kotlin sources (if any)
    if kotlin_srcs:
        kotlin_output = ctx.actions.declare_output("{}-kotlin.jar".format(ctx.attrs.name))
        _compile_kotlin(
            ctx,
            srcs = kotlin_srcs,
            classpath = classpath + [output_jar],
            output = kotlin_output,
        )

        # Merge Java and Kotlin outputs
        output_jar = _merge_jars(ctx, [output_jar, kotlin_output])

    return [
        DefaultInfo(default_output = output_jar),
        JavaInfo(
            compile_classpath = [output_jar],
            runtime_classpath = classpath + [output_jar],
        ),
    ]

def _compile_java(ctx, srcs, classpath, output, annotation_processors, annotation_processor_deps, annotation_processor_params, source_level, target_level):
    """Compile Java sources."""

    # Build javac command
    cmd = cmd_args()
    cmd.add("javac")
    cmd.add("-source", source_level)
    cmd.add("-target", target_level)
    cmd.add("-d", output.as_output())

    # Classpath
    if classpath:
        cmd.add("-classpath", cmd_args(classpath, delimiter = ":"))

    # Annotation processors
    if annotation_processors:
        ap_classpath = []
        for ap_dep in annotation_processor_deps:
            ap_classpath.extend(ap_dep[JavaInfo].runtime_classpath)

        cmd.add("-processorpath", cmd_args(ap_classpath, delimiter = ":"))
        cmd.add("-processor", ",".join(annotation_processors))

        # Annotation processor parameters
        for key, value in annotation_processor_params.items():
            cmd.add("-A{}={}".format(key, value))

    # Source files
    for src in srcs:
        cmd.add(src)

    ctx.actions.run(
        cmd,
        category = "javac",
    )

def _compile_kotlin(ctx, srcs, classpath, output):
    """Compile Kotlin sources."""

    cmd = cmd_args()
    cmd.add(ctx.attrs._kotlinc_tool)
    cmd.add("-jvm-target", ctx.attrs.target_level)
    cmd.add("-d", output.as_output())

    if classpath:
        cmd.add("-classpath", cmd_args(classpath, delimiter = ":"))

    for src in srcs:
        cmd.add(src)

    ctx.actions.run(
        cmd,
        category = "kotlinc",
    )

android_compile = rule(
    impl = _android_compile_impl,
    attrs = {
        "srcs": attrs.list(attrs.source(), default = [], doc = "Java and Kotlin source files"),
        "deps": attrs.list(attrs.dep(), default = [], doc = "Compilation dependencies"),

        # Compilation options
        "source_level": attrs.string(default = "11", doc = "Java source compatibility"),
        "target_level": attrs.string(default = "11", doc = "Java target compatibility"),

        # Annotation processors
        "annotation_processors": attrs.list(attrs.string(), default = [], doc = "Annotation processor classes"),
        "annotation_processor_deps": attrs.list(attrs.dep(), default = [], doc = "Annotation processor JARs"),
        "annotation_processor_params": attrs.dict(key = attrs.string(), value = attrs.string(), default = {}, doc = "AP parameters"),

        # Android SDK
        "platform_version": attrs.string(default = "33", doc = "Android platform version"),

        # Private SDK components
        "_android_jar": attrs.dep(
            default = "//android-sdk:platform_33",
        ),
        "_kotlinc_tool": attrs.exec_dep(
            default = "//kotlin-compiler:kotlinc",
        ),
    },
    doc = "Compiles Java and Kotlin sources for Android",
)
```

---

## Complete Integration with AGP

### Workflow: AGP Model → Buck2 Rules

**Step 1: Extract AGP Build Model**

```bash
./gradlew extractBuildModel --init-script init-extract-model.gradle
```

**Output:** `build/agp-build-model.json`

```json
{
  "debug": {
    "compileClasspath": [
      {"file": "/path/android.jar", "group": "com.android", "module": "android", "version": "33"},
      {"file": "/path/androidx.core.jar", "group": "androidx.core", "module": "core", "version": "1.9.0"}
    ],
    "annotationProcessors": [
      {"file": "/path/room-compiler.jar", "group": "androidx.room", "module": "room-compiler", "version": "2.5.0"}
    ],
    "annotationProcessorArguments": {
      "room.schemaLocation": "schemas/"
    },
    "sourceCompatibility": "VERSION_11",
    "minSdkVersion": 21
  }
}
```

**Step 2: Generate Buck2 Targets (Groovy Script)**

**File:** `scripts/generate-buck-targets.groovy`

```groovy
#!/usr/bin/env groovy
/**
 * Generates Buck2 BUCK files from AGP build model.
 * Uses modular SDK components and custom Starlark rules.
 */

import groovy.json.JsonSlurper

def modelFile = new File(args[0])
def model = new JsonSlurper().parseText(modelFile.text)

model.each { variantName, variantModel ->
    println "Generating Buck2 targets for variant: ${variantName}"

    def buckFile = new File("buck2-workspace/app/BUCK.${variantName}")

    buckFile.withWriter { writer ->
        writer.println "# Auto-generated from AGP build model"
        writer.println "# Variant: ${variantName}"
        writer.println ""

        // Generate prebuilt_jar rules for dependencies
        writer.println "# Dependencies"
        variantModel.compileClasspath.each { dep ->
            def targetName = "${dep.group}_${dep.module}".replaceAll(/[.-]/, '_')
            writer.println """
prebuilt_jar(
    name = "${targetName}",
    binary_jar = "${dep.file}",
    visibility = ["PUBLIC"],
)
"""
        }

        writer.println ""
        writer.println "# Annotation Processors"
        variantModel.annotationProcessors.each { ap ->
            def targetName = "ap_${ap.group}_${ap.module}".replaceAll(/[.-]/, '_')
            writer.println """
prebuilt_jar(
    name = "${targetName}",
    binary_jar = "${ap.file}",
    visibility = ["PUBLIC"],
)
"""
        }

        // Generate android_compile rule
        writer.println ""
        writer.println "# Compilation"
        writer.println """
load("//android-rules:android_compile.bzl", "android_compile")

android_compile(
    name = "compile_${variantName}",
    srcs = glob([
${variantModel.javaSourceDirs.collect { "        \"${it}/**/*.java\"," }.join('\n')}
${variantModel.kotlinSourceDirs.collect { "        \"${it}/**/*.kt\"," }.join('\n')}
    ]),
    deps = [
${variantModel.compileClasspath.collect { dep ->
            "        \":${dep.group}_${dep.module}\".replaceAll(/[.-]/, '_'),"
        }.join('\n')}
    ],
    source_level = "${variantModel.sourceCompatibility.replace('VERSION_', '')}",
    target_level = "${variantModel.targetCompatibility.replace('VERSION_', '')}",
    platform_version = "${variantModel.compileSdkVersion.replaceAll(/[^0-9]/, '')}",

    annotation_processors = [
${variantModel.annotationProcessors.collect { ap ->
            "        \"${ap.group}.${ap.module}.Processor\","  // Simplified
        }.join('\n')}
    ],
    annotation_processor_deps = [
${variantModel.annotationProcessors.collect { ap ->
            "        \":ap_${ap.group}_${ap.module}\".replaceAll(/[.-]/, '_'),"
        }.join('\n')}
    ],
    annotation_processor_params = {
${variantModel.annotationProcessorArguments.collect { k, v ->
            "        \"${k}\": \"${v}\","
        }.join('\n')}
    },
)
"""

        // Generate android_dex rule
        writer.println ""
        writer.println "# Dexing"
        writer.println """
load("//android-rules:android_dex.bzl", "android_dex")

android_dex(
    name = "dex_${variantName}",
    classes = [":compile_${variantName}"],
    deps = [
${variantModel.compileClasspath.collect { dep ->
            "        \":${dep.group}_${dep.module}\".replaceAll(/[.-]/, '_'),"
        }.join('\n')}
    ],
    min_sdk = ${variantModel.minSdkVersion},
    multi_dex = ${variantModel.multiDexEnabled},
    debug = ${variantModel.debuggable},
    d8_version = "33.0.0",
    platform_version = "${variantModel.compileSdkVersion.replaceAll(/[^0-9]/, '')}",
)
"""
    }

    println "  Generated: ${buckFile}"
}
```

**Usage:**
```bash
groovy scripts/generate-buck-targets.groovy build/agp-build-model.json
```

**Step 3: Build with Buck2**

```bash
buck2 build //app:compile_debug //app:dex_debug
```

**Step 4: Inject into AGP and Package**

```bash
export BUCK2_OUTPUT_DIR=buck2-out/gen/app
export AGP_VARIANT=debug
./gradlew assembleDebug --init-script init-bypass-compile-dex.gradle
```

---

## genrule vs Starlark vs BXL

### Comparison Matrix

| Feature | genrule | Starlark Rule | BXL |
|---------|---------|---------------|-----|
| **Ease of Use** | ⭐⭐⭐ Simple shell commands | ⭐⭐ Need to learn Starlark | ⭐ Most complex |
| **Type Safety** | ❌ String commands, no validation | ✅ Typed attributes | ✅ Full type system |
| **Reusability** | ❌ Copy-paste shell commands | ✅ Reusable rules | ✅ Highly reusable |
| **Debugging** | ❌ Shell errors are cryptic | ⭐⭐ Better error messages | ⭐⭐⭐ Best debugging |
| **Buck2 Integration** | ⭐⭐ Basic | ⭐⭐⭐ Full integration | ⭐⭐⭐ Advanced features |
| **Performance** | ⭐⭐ | ⭐⭐⭐ Optimized | ⭐⭐⭐ Most optimized |
| **Dependency Tracking** | ⭐⭐ Manual | ⭐⭐⭐ Automatic | ⭐⭐⭐ Advanced |

### When to Use Each

#### Use `genrule` when:
- ✅ Quick prototyping
- ✅ Simple file transformations
- ✅ One-off custom commands
- ❌ **NOT recommended for production Android builds**

**Example:**
```python
genrule(
    name = "quick_dex",
    srcs = [":classes.jar"],
    out = "classes.dex",
    cmd = "d8 --lib $ANDROID_JAR --output $OUT $SRCS",
)
```

#### Use **Starlark Rules** when:
- ✅ Building production Android apps (RECOMMENDED)
- ✅ Need type-safe, validated inputs
- ✅ Want reusable build components
- ✅ Team needs clear, maintainable build files

**Example:** (See `android_dex` rule above)

#### Use **BXL** when:
- ✅ Need advanced Buck2 features
- ✅ Dynamic dependency resolution
- ✅ Complex build orchestration
- ✅ Build analysis and introspection

**Example:**
```python
# dex.bxl
def _dex_impl(ctx):
    # Advanced: Query dependency graph
    all_deps = ctx.cquery().deps(ctx.target("//app:compile_debug"))

    # Filter only JAR dependencies
    jar_deps = [d for d in all_deps if d[DefaultInfo].default_outputs[0].extension == ".jar"]

    # Build DEX with all JARs
    # ... (advanced implementation)
```

### Recommendation for Android Builds

**Use Starlark Rules** (`android_compile`, `android_dex`, etc.) because:

1. ✅ **Type-safe** - Buck2 validates inputs at analysis time
2. ✅ **Modular** - Each rule is self-contained
3. ✅ **Maintainable** - Clear separation of concerns
4. ✅ **Cacheable** - Buck2 can optimize caching
5. ✅ **Hermetic** - Explicit SDK component dependencies
6. ✅ **Team-friendly** - Easy to understand and modify

---

## Summary

### Architecture Benefits

1. **Modular SDK Components**
   - Only download what you need (~85MB vs 30GB)
   - Hermetic builds (no $ANDROID_SDK_ROOT)
   - Version pinning per target

2. **Clean User-Facing Rules**
   - Declarative syntax
   - Hide implementation complexity
   - Easy to use from BUCK files

3. **Starlark Implementation**
   - Type-safe
   - Reusable
   - Buck2-optimized

4. **AGP Integration**
   - Extract build model from existing projects
   - Generate Buck2 targets automatically
   - No modification to source project

### File Structure

```
buck2-workspace/
├── android-sdk/
│   ├── BUCK                         # SDK component registry
│   └── sdk_component.bzl            # SDK extraction rule
│
├── android-rules/
│   ├── android_compile.bzl          # Compilation rule
│   ├── android_dex.bzl              # DEX conversion rule
│   └── android_resources.bzl        # Resource processing
│
├── app/
│   ├── BUCK.debug                   # Generated from AGP model
│   └── BUCK.release
│
└── scripts/
    └── generate-buck-targets.groovy # AGP model → Buck2 converter
```

### Next Steps

1. Implement `android_resources` rule (AAPT2)
2. Implement `android_package` rule (APK assembly)
3. Add R8/ProGuard support
4. Multi-module project support

---

**Tools Used:**
- fd, Bash, Write
- Tokens: ~5,000
- Files created: 1 (architecture documentation)
