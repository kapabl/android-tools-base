# Buck2 Modular Android SDK Architecture

## Table of Contents

1. [Overview](#overview)
2. [Problem Statement](#problem-statement)
3. [SDK Components by Build Phase](#sdk-components-by-build-phase)
4. [Modular SDK Component Extraction](#modular-sdk-component-extraction)
5. [Complete Integration with AGP](#complete-integration-with-agp)

---

## Overview

This document describes a **modular, hermetic Buck2 build system** for Android that:

1. **Extracts only needed Android SDK components** (no full 30GB SDK required)
2. **Provides clean, declarative Buck2 rules**
3. **Integrates with AGP-extracted build models**

**Note:** Examples in this document assume Android API 33. Java version depends on your project configuration (AGP 8.3 requires JDK 17 minimum).

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Buck2 Rules                               │
│  android_dex(classes=[...], deps=[...], d8_version="33.0.0") │
│  java_library(srcs=[...], deps=[...])                        │
│  gradle_deps(gradle_files=[...])                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ (depends on)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│           Modular Android SDK Components                     │
│  - D8 dexer (from build-tools)                               │
│  - android.jar (from platforms)                              │
│  - Platform tools as needed                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Problem Statement

### Traditional Approach Problems

**Typical Android SDK Installation:**
```
/opt/android-sdk/
├── platforms/              # ~500MB per platform × 3 versions = 1.5GB
├── build-tools/            # ~100MB per version × 3 versions = 300MB
├── system-images/          # ~1.5GB per image × 3 images = 4.5GB
├── emulator/               # ~500MB
├── platform-tools/         # ~20MB
├── sources/                # ~1GB (for 3 platforms)
└── ndk/                    # ~2GB (single version)
Total: ~10GB
```

**Note:** Full SDK with all platforms/images can reach ~30GB

**Problems:**
- ❌ CI/CD machines need full SDK installed
- ❌ Developers need same SDK version
- ❌ Slow CI setup (downloading/extracting ~10GB)

### Our Solution: Modular SDK Components

**Extract only what you need:**
```
buck2-android-sdk/
├── d8-33.0.0               # ~5MB (just the dexer)
├── platform-android-33     # ~70MB (just android.jar)
├── aapt2-33.0.0            # ~8MB (just resource compiler)
├── zipalign-33.0.0         # ~50KB
└── apksigner-33.0.0        # ~2MB
Total for typical build: ~84MB
```

**Benefits:**
- ✅ Explicit SDK component dependencies
- ✅ Fast CI/CD (download only what's needed)
- ✅ Remote caching (Buck2 caches SDK components)
- ✅ Version pinning (each target specifies exact versions)
- ✅ Parallel downloads (Buck2 fetches components in parallel)

---

## SDK Components by Build Phase

### 1. KAPT/Kotlin/Java Compilation Phase

**What Buck2 needs:**

```
java_library(
    name = "app_classes",
    srcs = [...],
    deps = [":deps"],
)
```

**Compilation order:** KAPT → Kotlin (compiles .kt + .java) → Java (pure .java only)

**KAPT (Kotlin Annotation Processing Tool):** Bridges Kotlin to Java annotation processors. Generates Kotlin stubs from `.kt` files, runs annotation processors (Room, Dagger, etc.) to generate Java code, then Kotlin compiler compiles everything together. KAPT runs before Kotlin compilation.

**SDK components required:**

| Component | Location in Full SDK | Size | Purpose |
|-----------|---------------------|------|---------|
| `android.jar` | `platforms/android-33/android.jar` | ~70MB | Android API classes for compilation |
| `core-lambda-stubs.jar` | `platforms/android-33/optional/core-lambda-stubs.jar` | ~50KB | Lambda desugaring stubs (if needed) |

**External (non-SDK):**
- Kotlin compiler (kotlinc) - ~50MB (if using Kotlin)
- Annotation processor JARs (Room, Dagger, etc.) - from Maven (if using KAPT/Java AP)

**Extraction:**
```
platforms/android-33/
├── android.jar                      # REQUIRED: Android API
├── framework.aidl                   # For AIDL compilation (see below)
├── optional/
│   └── core-lambda-stubs.jar        # OPTIONAL: Lambda desugaring
└── data/
    └── api-versions.xml             # OPTIONAL: Lint data
```

**Total: ~70MB** (vs 500MB full platform download)

---

### 2. AIDL (Android Interface Definition Language)

**What Buck2 needs:**

Converts `.aidl` files to Java interfaces.

**SDK components required:**

| Component | Location in Full SDK | Size | Purpose |
|-----------|---------------------|------|---------|
| `aidl` binary | `build-tools/33.0.0/aidl` | ~200KB | AIDL compiler binary |
| `framework.aidl` | `platforms/android-33/framework.aidl` | ~1MB | Android framework AIDL definitions |

**Extraction:**
```
build-tools/33.0.0/
└── aidl                             # REQUIRED: AIDL compiler

platforms/android-33/
└── framework.aidl                   # REQUIRED: Framework AIDL types
```

**Total: ~1.2MB**

---

### 3. DEX Conversion Phase

**What Buck2 needs:**

```
android_dex(
    name = "app_dex",
    classes = [":app_classes"],
    deps = [":deps"],
    d8_version = "33.0.0",
)
```

**SDK components required:**

| Component | Location in Full SDK | Size | Purpose |
|-----------|---------------------|------|---------|
| `d8` binary | `build-tools/33.0.0/d8` | ~50KB | D8 dexer wrapper script |
| `d8.jar` | `build-tools/33.0.0/lib/d8.jar` | ~4MB | D8 dexer implementation |
| `android.jar` | `platforms/android-33/android.jar` | ~70MB | Platform API for --lib flag |

**Extraction:**
```
build-tools/33.0.0/
├── d8                               # REQUIRED: D8 wrapper script
└── lib/
    ├── d8.jar                       # REQUIRED: D8 implementation
    └── (no other JARs needed)
```

**Total: ~4MB** (android.jar reused from compilation)

---

### 4. Resource Compilation (AAPT2)

**What Buck2 needs:**

Compiles Android resources (XML layouts, drawables, etc.).

**SDK components required:**

| Component | Location in Full SDK | Size | Purpose |
|-----------|---------------------|------|---------|
| `aapt2` binary | `build-tools/33.0.0/aapt2` | ~8MB | Resource compiler |
| `android.jar` | `platforms/android-33/android.jar` | ~70MB | Platform resources for linking |

**Extraction:**
```
build-tools/33.0.0/
└── aapt2                            # REQUIRED: AAPT2 binary
```

**Total: ~8MB** (android.jar reused)

---

### 5. APK Packaging (AGP handles this)

AGP still handles final APK assembly, signing, and zipalign.

**SDK components needed (by AGP, not Buck2):**

| Component | Location in Full SDK | Size | Purpose |
|-----------|---------------------|------|---------|
| `zipalign` | `build-tools/33.0.0/zipalign` | ~50KB | APK alignment tool |
| `apksigner.jar` | `build-tools/33.0.0/lib/apksigner.jar` | ~2MB | APK signing tool |

**Not extracted by Buck2** - AGP uses system SDK for these.

---

### Summary: Total SDK Extraction Size

| Phase | Components | Size |
|-------|-----------|------|
| **Compilation (KAPT/Kotlin/Java)** | android.jar, framework.aidl | ~71MB |
| **AIDL** | aidl binary | ~1.2MB |
| **DEX** | d8, d8.jar | ~4MB (android.jar reused) |
| **Resources** | aapt2 | ~8MB |
| **TOTAL** | | **~84MB** |

**vs Typical SDK:** ~10GB (119x reduction)
**vs Full SDK:** ~30GB (357x reduction)

---

## Modular SDK Component Extraction

### How It Works

Instead of requiring a typical ~10GB Android SDK installation (or ~30GB for full SDK), Buck2 can download only the specific components needed for each build phase:

1. **HTTP Archive downloads** - Buck2 downloads SDK ZIP files from Google's Android repository
2. **Selective extraction** - Only extract the specific binaries/JARs needed (d8, android.jar, etc.)
3. **CAS caching** - Downloaded components are cached in Buck2's content-addressable storage
4. **Filegroup exposure** - Extracted components are exposed as Buck2 filegroup targets

### Example SDK Component Definitions

See sample SDK component extraction rules (future implementation):

```
docs/sample-repo-structure/
└── buck2-workspace/
    └── android-sdk/
        ├── BUCK                     # SDK component registry
        └── sdk_component.bzl        # (future) Component extraction rule
```

**Current approach:** Download full SDK components, then use filegroups to expose only needed pieces.

**Example BUCK file** for exposing SDK components:

```python
# android-sdk/BUCK

# D8 dexer from build-tools 33.0.0
filegroup(
    name = "d8_binary",
    srcs = ["build-tools/33.0.0/d8"],
    visibility = ["PUBLIC"],
)

filegroup(
    name = "d8_jar",
    srcs = ["build-tools/33.0.0/lib/d8.jar"],
    visibility = ["PUBLIC"],
)

# Android platform 33
filegroup(
    name = "android_jar_33",
    srcs = ["platforms/android-33/android.jar"],
    visibility = ["PUBLIC"],
)

filegroup(
    name = "framework_aidl_33",
    srcs = ["platforms/android-33/framework.aidl"],
    visibility = ["PUBLIC"],
)

# AAPT2 resource compiler
filegroup(
    name = "aapt2",
    srcs = ["build-tools/33.0.0/aapt2"],
    visibility = ["PUBLIC"],
)
```

---

## Buck2 Rules Usage

### android_dex Rule

```python
android_dex(
    name = "app_dex",
    classes = [":app_classes"],
    deps = [":deps"],
    d8_version = "33.0.0",
    platform_version = "33",
    min_sdk = 21,
    multi_dex = False,
    debug = True,
    enable_desugaring = True,
)
```

**SDK components used:**
- `//android-sdk:d8_binary` + `//android-sdk:d8_jar` → D8 dexer
- `//android-sdk:android_jar_33` → android.jar (for --lib flag)

---

### java_library Rule

For Java/Kotlin compilation, use Buck2's built-in `java_library`:

```python
java_library(
    name = "app_classes",
    srcs = [
        "//:app_java_sources",
        "//:app_kotlin_sources",
        "//:app_generated_sources",
    ],
    deps = [":deps"],
    source = "17",
    target = "17",
)
```

**SDK components used:**
- `//android-sdk:android_jar_33` → android.jar (bootclasspath)

---

## Complete Integration with AGP

### Workflow: AGP Model → Buck2 Targets

**Step 1: Extract AGP Build Model**

See sample init-script:

```
docs/sample-repo-structure/android/build/buck2/gradle/init-scripts/
└── init-extract-model.gradle
```

**Step 2: Generate Buck2 Targets**

See sample Python script:

```
docs/sample-repo-structure/android/build/buck2/
└── generate-android-build-targets.py
```

**Step 3: Build with Buck2**

```bash
buck2 build //android/build/buck2:app_classes //android/build/buck2:app_dex
```

**Step 4: Inject into AGP and Package**

```bash
export BUCK2_OUTPUT_DIR=../../buck2-out/gen/android/build/buck2
cd android/app
../../gradlew assembleDebug --init-script ../../build/buck2/gradle/init-scripts/init-bypass-compile-dex.gradle
```

---

## Summary

### Architecture Benefits

1. **Modular SDK Components**
   - Only download what you need (~84MB vs ~10GB typical SDK)
   - Version pinning per target
   - Explicit component dependencies

2. **Clean Buck2 Rules**
   - Declarative syntax
   - Easy to use from BUCK files

3. **AGP Integration**
   - Extract build model from existing projects
   - Generate Buck2 targets automatically (Python script)
   - No modification to source project

### File Structure

See `docs/sample-repo-structure/` for example files.

### Next Steps

1. Implement AAPT2 resource compilation
2. Add R8/ProGuard support
3. Multi-module project support
