# Buck2 NDK r28b Extraction & Cross-Platform Analysis

**Source:** Verified against actual NDK r28b archives for all 3 platforms at `/home/kapablanka/repos/ndk_r28b/`.

## Table of Contents

1. [NDK r28b Structure](#ndk-r28b-structure)
2. [Platform Differences (Linux vs macOS vs Windows)](#platform-differences)
3. [NDK Components by Build Phase](#ndk-components-by-build-phase)
4. [Targeted Slicing Strategy](#targeted-slicing-strategy)
5. [Cross-Compilation Matrix](#cross-compilation-matrix)
6. [Buck2 Rules](#buck2-rules)

---

## NDK r28b Structure

NDK r28b uses a **unified LLVM/Clang 19 toolchain** (unified since r19+). The actual binary is `clang-19` — `clang` is a symlink (Linux/macOS) or renamed `.exe` (Windows).

```
ndk-r28b/
├── meta/
│   └── abis.json                          # ABI metadata (identical across platforms)
├── build/
│   └── cmake/
│       └── android.toolchain.cmake        # CMake toolchain file
├── ndk-build                              # Shell script (Linux/macOS) | ndk-build.cmd (Windows)
├── ndk-gdb                                # Shell script | ndk-gdb.cmd (Windows)
├── ndk-lldb                               # Shell script | ndk-lldb.cmd (Windows)
├── ndk-stack                              # Shell script | ndk-stack.cmd (Windows)
├── ndk-which                              # Shell script | ndk-which.cmd (Windows)
├── toolchains/
│   └── llvm/
│       └── prebuilt/
│           └── {host-tag}/                # linux-x86_64 | darwin-x86_64 | windows-x86_64
│               ├── bin/                   # Compiler + LLVM tools (747MB linux, 1.3GB darwin/win)
│               ├── lib/                   # Compiler runtime + builtins (987MB linux, 1.2GB darwin, 510MB win)
│               ├── libexec/               # Internal compiler support
│               ├── sysroot/               # Headers + platform libs (256MB, IDENTICAL across hosts)
│               │   ├── usr/include/       # 2611 headers (linux) / 2603 (darwin/win)
│               │   └── usr/lib/           # 1811 files, IDENTICAL across all hosts
│               │       ├── aarch64-linux-android/
│               │       ├── arm-linux-androideabi/
│               │       ├── i686-linux-android/
│               │       ├── x86_64-linux-android/
│               │       └── riscv64-linux-android/
│               ├── python3/               # Python for build scripts
│               ├── share/                 # CMake modules, etc.
│               ├── include/               # Host-side clang includes
│               └── musl/                  # LINUX ONLY: musl cross-compile libs
├── sources/
│   └── android/
│       └── native_app_glue/               # Helper sources
├── shader-tools/
│   └── {host-tag}/                        # glslc, spirv-* tools (.exe on Windows)
├── simpleperf/                            # Profiling tool
├── prebuilt/
│   └── {host-tag}/
│       └── bin/
│           ├── make                       # GNU Make (.exe on Windows)
│           ├── yasm                       # Assembler (.exe on Windows)
│           └── ...                        # Windows also has cmp.exe, echo.exe
├── python-packages/                       # Python support
└── wrap.sh                                # Wrapper script
```

### Verified Sizes

| Platform | bin/ | lib/ | sysroot/ | Total NDK |
|---|---|---|---|---|
| **Linux** | 747MB | 987MB | 256MB | **2.2GB** |
| **macOS** | 1.3GB | 1.2GB | 256MB | **2.8GB** |
| **Windows** | 1.3GB | 510MB | 256MB | **2.2GB** |

macOS is largest because `clang-19` is a **universal binary** (x86_64 + arm64 = 165MB vs 130MB Linux / 123MB Windows).

---

## Platform Differences

### Top-Level Scripts

| Script | Linux | macOS | Windows |
|---|---|---|---|
| ndk-build | `ndk-build` (shell) | `ndk-build` (shell) | `ndk-build.cmd` (batch) |
| ndk-gdb | `ndk-gdb` (shell) | `ndk-gdb` (shell) | `ndk-gdb.cmd` (batch) |
| ndk-lldb | `ndk-lldb` (shell) | `ndk-lldb` (shell) | `ndk-lldb.cmd` (batch) |
| ndk-stack | `ndk-stack` (shell) | `ndk-stack` (shell) | `ndk-stack.cmd` (batch) |
| ndk-which | `ndk-which` (shell) | `ndk-which` (shell) | `ndk-which.cmd` (batch) |

### Toolchain Binaries (`toolchains/llvm/prebuilt/{host}/bin/`)

| Tool | Linux (181 files) | macOS (179 files) | Windows (295 files) |
|---|---|---|---|
| **clang** | `clang` → symlink to `clang-19` (ELF, 130MB) | `clang` → symlink to `clang-19` (Mach-O universal x86_64+arm64, 165MB) | `clang.exe` (PE32+, 123MB) — **no bare `clang`** |
| **clang++** | `clang++` (symlink) | `clang++` (symlink) | `clang++.exe` |
| **ld.lld** | `ld.lld` | `ld.lld` | `ld.lld.exe` |
| **llvm-ar** | `llvm-ar` | `llvm-ar` | `llvm-ar.exe` |
| **llvm-strip** | `llvm-strip` | `llvm-strip` | `llvm-strip.exe` |
| **llvm-objcopy** | `llvm-objcopy` | `llvm-objcopy` | `llvm-objcopy.exe` |
| **llvm-nm** | `llvm-nm` | `llvm-nm` | `llvm-nm.exe` |
| **llvm-readelf** | `llvm-readelf` | `llvm-readelf` | `llvm-readelf.exe` |
| **llvm-ranlib** | `llvm-ranlib` | `llvm-ranlib` | `llvm-ranlib.exe` |

**46 `.exe` files** on Windows, rest are versioned clang wrappers as `.cmd` batch files.

### Versioned Clang Wrappers (target-specific convenience scripts)

These exist for every ABI × API level combination (e.g., `aarch64-linux-android21-clang` through `aarch64-linux-android35-clang`):

| Platform | Format | Example |
|---|---|---|
| Linux | Bash script | `aarch64-linux-android21-clang` |
| macOS | Bash script | `aarch64-linux-android21-clang` |
| Windows | `.cmd` batch script **AND** extensionless script | `aarch64-linux-android21-clang.cmd` + `aarch64-linux-android21-clang` |

**Windows has BOTH**: the `.cmd` and a bare-name copy for each wrapper, explaining the 295 file count (nearly 2x).

### Platform-Exclusive Binaries

| Binary | Linux | macOS | Windows | Notes |
|---|---|---|---|---|
| `clang-19` | YES | YES | NO | Actual compiler binary; Windows uses `clang.exe` directly |
| `bisect_driver.py` | YES | NO | NO | Bisection helper |
| `clang-tidy.sh` | YES | NO | NO | Tidy wrapper |
| `clangd` | YES | NO | NO | LSP server |
| `clang-cl` | NO | YES | YES (`.exe`) | MSVC-compatible driver |
| `ld64.lld` | YES | NO | NO | macOS linker backend |
| `lld` | YES | NO | NO | Generic LLD entry |
| `lld-link` | YES | NO | NO | COFF linker |
| `llvm-bolt` | YES | NO | NO | Binary optimizer |
| `lldb.sh` | YES | NO | NO | LLDB wrapper |
| `lldb.exe` | NO | NO | YES | Debugger (Windows) |
| `liblldb.dll` | NO | NO | YES | LLDB shared lib |
| `libwinpthread-1.dll` | NO | NO | YES | Windows threading DLL |
| `libxml2.dll` | NO | NO | YES | Windows XML DLL |
| `scan-build` | YES | NO | NO | Static analyzer |
| `scan-view` | YES | NO | NO | Static analyzer viewer |
| `remote_toolchain_inputs` | YES | NO | NO | Remote build support |
| `merge-fdata` | YES | NO | NO | BOLT data merger |

### `lib/` Directory Differences

| Content | Linux (987MB) | macOS (1.2GB) | Windows (510MB) |
|---|---|---|---|
| `clang/` (compiler builtins) | YES — target-specific builtins for all Android ABIs | YES | YES |
| `musl` cross-compile libs | YES (`aarch64-unknown-linux-musl/`, `i686-unknown-linux-musl/`, etc.) | NO | NO |
| `i386-unknown-linux-gnu/` | YES (host-side libc++ for 32-bit Linux) | NO | NO |
| `libclang-cpp.so` / `libclang.so` | YES (shared libs for clang tooling) | NO (different format) | NO |
| `libc++.a`, `libc++abi.a` | YES (in multiple host-specific paths) | YES | YES (host-level only) |
| `liblldb.*` | YES (`.so`) | YES (`.dylib`) | YES (`.dll` in bin/) |

**Key: Linux has extra musl and host-side cross-compile libraries not present on macOS/Windows.**

### Sysroot Headers

| | Linux | macOS | Windows |
|---|---|---|---|
| Header count | **2611** | **2603** | **2603** |
| Difference | +8 netfilter headers | identical to Windows | identical to macOS |

The 8 extra Linux headers are **case-sensitive duplicates** of existing lowercase headers:

```
usr/include/linux/netfilter_ipv4/ipt_ECN.h    (vs ipt_ecn.h)
usr/include/linux/netfilter_ipv4/ipt_TTL.h    (vs ipt_ttl.h)
usr/include/linux/netfilter_ipv6/ip6t_HL.h    (vs ip6t_hl.h)
usr/include/linux/netfilter/xt_CONNMARK.h      (vs xt_connmark.h)
usr/include/linux/netfilter/xt_DSCP.h          (vs xt_dscp.h)
usr/include/linux/netfilter/xt_MARK.h          (vs xt_mark.h)
usr/include/linux/netfilter/xt_RATEEST.h       (vs xt_rateest.h)
usr/include/linux/netfilter/xt_TCPMSS.h        (vs xt_tcpmss.h)
```

These can't coexist on case-insensitive filesystems (macOS HFS+/APFS default, Windows NTFS).

### Sysroot Platform Libs (`sysroot/usr/lib/`)

| | Linux | macOS | Windows |
|---|---|---|---|
| File count | **1811** | **1811** | **1811** |
| File list diff | — | **IDENTICAL** | **IDENTICAL** |

**100% identical** across all 3 platforms. Same filenames, same structure.

### Other Directories

| Directory | Platform Difference |
|---|---|
| `meta/abis.json` | **IDENTICAL** across all 3 |
| `sources/` | **IDENTICAL** |
| `build/cmake/` | **IDENTICAL** |
| `shader-tools/` | Same tools, host-specific dir name, `.exe` on Windows |
| `simpleperf/` | Same tools; `inferno.sh` (Linux/macOS) vs `inferno.bat` (Windows) |
| `prebuilt/{host}/bin/` | Same tools + `.exe`; Windows adds `cmp.exe`, `echo.exe` |

### ABI Metadata (`meta/abis.json` — IDENTICAL)

| ABI | Triple | LLVM Triple | Bitness | Default | Min API |
|---|---|---|---|---|---|
| `armeabi-v7a` | `arm-linux-androideabi` | `armv7-none-linux-androideabi` | 32 | YES | 21 |
| `arm64-v8a` | `aarch64-linux-android` | `aarch64-none-linux-android` | 64 | YES | 21 |
| `x86` | `i686-linux-android` | `i686-none-linux-android` | 32 | YES | 21 |
| `x86_64` | `x86_64-linux-android` | `x86_64-none-linux-android` | 64 | YES | 21 |
| `riscv64` | `riscv64-linux-android` | `riscv64-none-linux-android` | 64 | NO | **35** |

---

## NDK Components by Build Phase

### Phase 1: C/C++ Compilation (clang/clang++)

| Component | Path | Purpose |
|---|---|---|
| `clang-19` / `clang.exe` | `bin/clang-19` or `bin/clang.exe` | Compiler binary (130MB linux, 165MB darwin, 123MB win) |
| `clang++` | `bin/clang++` or `bin/clang++.exe` | C++ compiler (symlink/copy of clang) |
| Sysroot headers | `sysroot/usr/include/` | C/C++ standard + POSIX + Android headers |
| Per-ABI asm headers | `sysroot/usr/include/{triple}/` | ABI-specific `asm/`, `machine/` headers |
| Platform libs (CRT) | `sysroot/usr/lib/{triple}/{api}/` | `crtbegin_so.o`, `crtend_so.o` |
| Compiler builtins | `lib/clang/*/lib/linux/` | `libclang_rt.builtins-*.a` |
| CMake toolchain | `build/cmake/android.toolchain.cmake` | CMake integration |

### Phase 2: Linking (ld.lld)

| Component | Path | Purpose |
|---|---|---|
| `ld.lld` | `bin/ld.lld{.exe}` | LLVM linker |
| Platform libs | `sysroot/usr/lib/{triple}/{api}/` | `libc.so`, `libm.so`, `liblog.so`, `libandroid.so`, etc. |

### Phase 3: Post-processing

| Component | Path | Purpose |
|---|---|---|
| `llvm-strip` | `bin/llvm-strip{.exe}` | Remove debug symbols for release |
| `llvm-objcopy` | `bin/llvm-objcopy{.exe}` | Extract debug info for symbolication |

### Phase 4: STL Packaging

| Component | Path | Purpose |
|---|---|---|
| `libc++_shared.so` | `sysroot/usr/lib/{triple}/libc++_shared.so` | Shipped in APK if using c++_shared STL |

### Phase 5: Shader Compilation (optional)

| Component | Path | Purpose |
|---|---|---|
| `glslc` | `shader-tools/{host}/glslc{.exe}` | GLSL to SPIR-V compiler |
| `spirv-*` | `shader-tools/{host}/spirv-*{.exe}` | SPIR-V tools |

---

## Targeted Slicing Strategy

### Dimensions

**Dimension 1 — Target ABI** (what you compile FOR = Android device):

| Target | ABI | Common Use |
|---|---|---|
| Android ARM64 | `arm64-v8a` | 99%+ of Android devices |
| Android ARM32 | `armeabi-v7a` | Legacy devices |
| Android x86_64 | `x86_64` | Emulators, ChromeOS |
| Android x86 | `x86` | Old emulators |
| Android RISC-V | `riscv64` | Experimental (min API 35) |

**Dimension 2 — Executor** (what HOST runs the build):

| Executor | Host Tag | Runs On |
|---|---|---|
| Linux x86_64 | `linux-x86_64` | CI, Linux dev machines |
| macOS x86_64/arm64 | `darwin-x86_64` | Mac dev machines (universal binary handles arm64 via Rosetta) |
| Windows x86_64 | `windows-x86_64` | Windows dev machines |

### Slicing Formula

```
ndk_slice = host_tools(executor) + headers(shared) + platform_libs(target_abi, api_level)
```

### Slice 1: Host Toolchain (EXECUTOR-dependent, TARGET-independent)

3 variants — one per executor platform. Only the binaries that Buck2 actually invokes:

```
ndk-toolchain-linux/          # or darwin, windows
├── bin/
│   ├── clang-19              # (or clang.exe on Windows)
│   ├── clang → clang-19      # symlink (Linux/macOS only)
│   ├── clang++ → clang-19    # symlink (Linux/macOS), clang++.exe (Windows)
│   ├── ld.lld                # (.exe on Windows)
│   ├── llvm-ar               # (.exe on Windows)
│   ├── llvm-strip            # (.exe on Windows)
│   ├── llvm-objcopy          # (.exe on Windows)
│   └── llvm-ranlib           # (.exe on Windows)
├── lib/
│   └── clang/{version}/lib/linux/  # Compiler builtins per target ABI
└── libexec/                        # Internal compiler support
```

### Slice 2: Headers (SHARED — platform-independent)

1 copy, used by all builds. Identical across all host platforms (minus 8 case-sensitive netfilter headers on Linux that are irrelevant for Android development):

```
ndk-headers/
└── usr/include/
    ├── android/              # Android-specific (NativeActivity, etc.)
    ├── c++/v1/               # libc++ headers
    ├── linux/                # Linux kernel UAPI headers
    ├── aarch64-linux-android/    # arm64 asm headers
    ├── arm-linux-androideabi/    # arm32 asm headers
    ├── i686-linux-android/       # x86 asm headers
    ├── x86_64-linux-android/     # x86_64 asm headers
    └── riscv64-linux-android/    # riscv64 asm headers
```

### Slice 3: Platform Libs (TARGET-dependent, EXECUTOR-independent)

Per target ABI + API level. 100% identical across host platforms:

```
ndk-sysroot-{abi}-{api}/     # e.g., ndk-sysroot-arm64-v8a-21
├── crtbegin_so.o
├── crtend_so.o
├── crtbegin_dynamic.o
├── crtend_android.o
├── libc.so
├── libm.so
├── liblog.so
├── libandroid.so
├── libdl.so
├── libz.so
├── libEGL.so
├── libGLESv3.so
├── libvulkan.so
└── ...
```

Plus STL at the ABI root (not API-versioned):

```
ndk-stl-{abi}/
└── libc++_shared.so          # ~800KB, for APK packaging with c++_shared
```

### Slice 4: Build System Support (optional)

```
ndk-build-support/
├── build/cmake/android.toolchain.cmake
├── meta/abis.json
└── ndk-build{.cmd}           # + build/core/*.mk makefiles (if using ndk-build)
```

---

## Cross-Compilation Matrix

All NDK compilation is cross-compilation (host → Android). The compiler runs on the host and outputs Android-targeted ELF binaries.

### Executor → Target (all combinations work)

| | arm64-v8a | armeabi-v7a | x86_64 | x86 | riscv64 |
|---|---|---|---|---|---|
| **Linux executor** | YES | YES | YES | YES | YES |
| **macOS executor** | YES | YES | YES | YES | YES |
| **Windows executor** | YES | YES | YES | YES | YES |

**Every executor can build for every target.** The `.so` output is identical regardless of which host built it (hermetic).

### What Varies Between Executors

| Aspect | Linux | macOS | Windows |
|---|---|---|---|
| Binary format | ELF | Mach-O (universal x86_64+arm64) | PE32+ |
| Binary suffix | none | none | `.exe` |
| Clang binary | `clang` → symlink → `clang-19` | `clang` → symlink → `clang-19` | `clang.exe` (no symlink, no `clang-19`) |
| Wrapper scripts | Bash | Bash | `.cmd` batch |
| Extra host libs | musl cross-compile, BOLT, scan-build | — | libwinpthread-1.dll, libxml2.dll, liblldb.dll |
| Path separator | `/` | `/` | `\` |

### What Is Identical Across Executors

- `meta/abis.json` (ABI definitions)
- `sysroot/usr/lib/` (1811 platform libs — verified identical)
- `sysroot/usr/include/` (2603 headers — identical; Linux has 8 extra case-sensitive netfilter headers)
- `sources/` (helper source code)
- `build/cmake/android.toolchain.cmake`
- Compiler flags for same target
- Output `.so` binaries

---

## Buck2 Rules

### NDK Toolchain Definition

```python
# android-ndk/BUCK

# Host toolchain binaries (executor-specific)
# Note: Linux/macOS use symlink clang→clang-19, Windows uses clang.exe directly
filegroup(
    name = "clang",
    srcs = select({
        "//config:linux": ["toolchains/llvm/prebuilt/linux-x86_64/bin/clang"],
        "//config:macos": ["toolchains/llvm/prebuilt/darwin-x86_64/bin/clang"],
        "//config:windows": ["toolchains/llvm/prebuilt/windows-x86_64/bin/clang.exe"],
    }),
    visibility = ["PUBLIC"],
)

filegroup(
    name = "clang++",
    srcs = select({
        "//config:linux": ["toolchains/llvm/prebuilt/linux-x86_64/bin/clang++"],
        "//config:macos": ["toolchains/llvm/prebuilt/darwin-x86_64/bin/clang++"],
        "//config:windows": ["toolchains/llvm/prebuilt/windows-x86_64/bin/clang++.exe"],
    }),
    visibility = ["PUBLIC"],
)

filegroup(
    name = "lld",
    srcs = select({
        "//config:linux": ["toolchains/llvm/prebuilt/linux-x86_64/bin/ld.lld"],
        "//config:macos": ["toolchains/llvm/prebuilt/darwin-x86_64/bin/ld.lld"],
        "//config:windows": ["toolchains/llvm/prebuilt/windows-x86_64/bin/ld.lld.exe"],
    }),
    visibility = ["PUBLIC"],
)

filegroup(
    name = "llvm_strip",
    srcs = select({
        "//config:linux": ["toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip"],
        "//config:macos": ["toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-strip"],
        "//config:windows": ["toolchains/llvm/prebuilt/windows-x86_64/bin/llvm-strip.exe"],
    }),
    visibility = ["PUBLIC"],
)

filegroup(
    name = "llvm_objcopy",
    srcs = select({
        "//config:linux": ["toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-objcopy"],
        "//config:macos": ["toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-objcopy"],
        "//config:windows": ["toolchains/llvm/prebuilt/windows-x86_64/bin/llvm-objcopy.exe"],
    }),
    visibility = ["PUBLIC"],
)

# Shared headers (platform-independent — pick any host, they're identical)
filegroup(
    name = "sysroot_headers",
    srcs = glob(["toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/include/**"]),
    visibility = ["PUBLIC"],
)

# Per-ABI platform libs (identical across hosts)
filegroup(
    name = "sysroot_arm64_v8a_21",
    srcs = glob([
        "toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/21/*",
        "toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so",
    ]),
    visibility = ["PUBLIC"],
)

filegroup(
    name = "sysroot_armeabi_v7a_21",
    srcs = glob([
        "toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/arm-linux-androideabi/21/*",
        "toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/arm-linux-androideabi/libc++_shared.so",
    ]),
    visibility = ["PUBLIC"],
)

filegroup(
    name = "sysroot_x86_64_21",
    srcs = glob([
        "toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/x86_64-linux-android/21/*",
        "toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/x86_64-linux-android/libc++_shared.so",
    ]),
    visibility = ["PUBLIC"],
)

filegroup(
    name = "sysroot_x86_21",
    srcs = glob([
        "toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/i686-linux-android/21/*",
        "toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/i686-linux-android/libc++_shared.so",
    ]),
    visibility = ["PUBLIC"],
)

# CMake toolchain file
filegroup(
    name = "cmake_toolchain",
    srcs = ["build/cmake/android.toolchain.cmake"],
    visibility = ["PUBLIC"],
)

# ABI metadata
filegroup(
    name = "abi_metadata",
    srcs = ["meta/abis.json"],
    visibility = ["PUBLIC"],
)
```

### Usage: Compile Native Code

```python
# Example: compile a C++ shared library for arm64-v8a
genrule(
    name = "hello_arm64",
    srcs = ["hello.cpp"],
    out = "libhello.so",
    cmd = """
        $(exe //android-ndk:clang++) \
            --target=aarch64-linux-android21 \
            --sysroot=$(location //android-ndk:sysroot_headers)/.. \
            -shared -o $OUT $SRCS
    """,
)
```

### Slice Summary

| Slice | Variants | Size | What Varies |
|---|---|---|---|
| **Host toolchain** | 3 (linux, darwin, windows) | 747MB–1.3GB each | Binary format, `.exe` suffix, symlinks vs copies |
| **Headers** | 1 (shared) | part of 256MB sysroot | 8 netfilter headers Linux-only (irrelevant) |
| **Platform libs** | per ABI × API level | part of 256MB sysroot | Nothing — 100% identical across hosts |
| **Build support** | 1 (shared) | <1MB | cmake toolchain, abis.json |
| **Shader tools** | 3 (per host) | ~20MB each | `.exe` on Windows |

### What Buck2 Actually Needs (minimum viable slice)

For compiling + linking a `.so` for a single ABI on a single executor:

| Component | Required |
|---|---|
| `bin/clang-19` (or `clang.exe`) | YES |
| `bin/ld.lld` (or `ld.lld.exe`) | YES (invoked by clang) |
| `lib/clang/*/lib/linux/{abi}/` | YES (compiler builtins) |
| `sysroot/usr/include/` | YES (headers) |
| `sysroot/usr/lib/{triple}/{api}/` | YES (CRT + platform libs) |
| `bin/llvm-strip` | RELEASE ONLY |
| `bin/llvm-objcopy` | DEBUG INFO ONLY |
| Everything else | NO |

---

## Related Documentation

- **[BUCK2_ANDROID_SDK_EXTRACTIONS.md](./BUCK2_ANDROID_SDK_EXTRACTIONS.md)** - SDK extraction (Java/DEX tools)
- **[BUCK2_INTEGRATION.md](./BUCK2_INTEGRATION.md)** - Overall Buck2 + AGP architecture
