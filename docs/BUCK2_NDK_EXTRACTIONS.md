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

#### Sharing Headers Across Executors (Linux ↔ macOS hybrid builds)

The 8 uppercase headers are **not a problem** for sharing a single header set across all executors. Verified:

1. **No NDK header `#include`s the uppercase files.** Searched all 2611 headers — zero results. They are never referenced by the NDK's own include graph.

2. **The uppercase headers are just compat wrappers** that redirect to the lowercase versions:
   ```c
   // xt_DSCP.h — just includes the lowercase version
   #include <linux/netfilter/xt_dscp.h>

   // xt_CONNMARK.h — same pattern
   #include <linux/netfilter/xt_connmark.h>
   ```
   Only `ipt_ECN.h`, `ipt_TTL.h`, `ip6t_HL.h`, and `xt_RATEEST.h` contain their own definitions (for legacy Linux netfilter userspace APIs — not relevant to Android app development).

3. **Linux has BOTH uppercase and lowercase.** The lowercase headers exist on all 3 platforms and contain the actual definitions. The uppercase ones are extras.

4. **If user code `#include`s an uppercase header, it would fail on macOS/Windows anyway** — this is a known Linux kernel UAPI quirk, not an NDK portability expectation.

**Solution: Use the macOS/Darwin header set (2603 files) as the shared baseline for all executors.** It is a strict subset of Linux's set. No wrappers, symlinks, or case-folding needed.

```python
# In Buck2: one shared header filegroup works for ALL executors
# Use darwin (or windows) as source — they have the portable 2603-file set
# Linux executors work fine because all actual definitions are in lowercase headers
filegroup(
    name = "sysroot_headers",
    srcs = glob(["sysroot/usr/include/**"]),  # 2603 files, works on linux/mac/win
    visibility = ["PUBLIC"],
)
```

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

# Compiler builtins — per target ABI, drop ABIs you don't build for
# These are under lib/clang/19/lib/linux/{arch}/ — 32-38MB each
filegroup(
    name = "builtins_arm64",
    srcs = glob(["toolchains/llvm/prebuilt/linux-x86_64/lib/clang/19/lib/linux/aarch64/**"]),
    visibility = ["PUBLIC"],
)

filegroup(
    name = "builtins_x86_64",
    srcs = glob(["toolchains/llvm/prebuilt/linux-x86_64/lib/clang/19/lib/linux/x86_64/**"]),
    visibility = ["PUBLIC"],
)

# Builtin headers (always needed, 15MB)
filegroup(
    name = "builtin_headers",
    srcs = glob(["toolchains/llvm/prebuilt/linux-x86_64/lib/clang/19/include/**"]),
    visibility = ["PUBLIC"],
)

# Shared sysroot headers (platform-independent — pick any host, they're identical)
# Keep all 24MB — not worth slicing (headers #include each other transitively)
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

### ABI-Aware NDK Rule (`ndk_toolchain.bzl`)

This `.bzl` rule ensures only the needed ABI's builtins + sysroot are sent to the executor:

```python
# ndk_toolchain.bzl

# ABI → compiler builtin dir mapping
_ABI_BUILTIN_ARCH = {
    "arm64-v8a": "aarch64",
    "armeabi-v7a": "arm",
    "x86_64": "x86_64",
    "x86": "i386",
    "riscv64": "riscv64",
}

# ABI → sysroot triple mapping
_ABI_TRIPLE = {
    "arm64-v8a": "aarch64-linux-android",
    "armeabi-v7a": "arm-linux-androideabi",
    "x86_64": "x86_64-linux-android",
    "x86": "i686-linux-android",
    "riscv64": "riscv64-linux-android",
}

# ABI → clang target flag
_ABI_TARGET = {
    "arm64-v8a": "aarch64-linux-android",
    "armeabi-v7a": "armv7a-linux-androideabi",
    "x86_64": "x86_64-linux-android",
    "x86": "i686-linux-android",
    "riscv64": "riscv64-linux-android",
}

# Size per ABI builtin (measured from NDK r28b):
#   aarch64: 35MB, arm: 32MB, i386: 32MB, x86_64: 33MB, riscv64: 38MB
# Total all 5: 370MB. Picking 1 ABI saves ~135MB, picking 2 saves ~102MB.

def ndk_cc_toolchain(
    name,
    abi,                    # e.g. "arm64-v8a"
    api_level = 21,         # minimum Android API
    ndk_path = "//android-ndk",
):
    """Defines a C/C++ toolchain for a single Android ABI.

    Only the builtins and sysroot for the specified ABI are included
    as inputs, so Buck2 only sends what the executor needs.
    """
    arch = _ABI_BUILTIN_ARCH[abi]
    triple = _ABI_TRIPLE[abi]
    target = _ABI_TARGET[abi]

    native.cxx_toolchain(
        name = name,
        compiler = ndk_path + ":clang",
        compiler_type = "clang",
        cxx_compiler = ndk_path + ":clang++",
        linker = ndk_path + ":lld",
        archiver = ndk_path + ":llvm_ar",
        strip = ndk_path + ":llvm_strip",

        # Only this ABI's builtins are sent to executor (~32-38MB, not all 370MB)
        compiler_flags = [
            "--target={}{}".format(target, api_level),
            "--sysroot=$(location {}:sysroot_headers)/..".format(ndk_path),
        ],

        # Inputs sent to executor — this is the key slicing:
        additional_inputs = [
            # Host tools (executor-specific, selected by select() in BUCK)
            ndk_path + ":clang",
            ndk_path + ":clang++",
            ndk_path + ":lld",

            # Builtin headers (15MB, always needed)
            ndk_path + ":builtin_headers",

            # THIS ABI's builtins only (32-38MB instead of 370MB)
            ndk_path + ":builtins_{}".format(abi.replace("-", "_")),

            # Sysroot headers (24MB, all included — not worth slicing)
            ndk_path + ":sysroot_headers",

            # THIS ABI's platform libs only (~664KB for single API level)
            ndk_path + ":sysroot_{}_{}".format(abi.replace("-", "_"), api_level),
        ],
    )
```

### BUCK file using the rule

```python
# BUCK

load(":ndk_toolchain.bzl", "ndk_cc_toolchain")

# Only arm64-v8a + x86_64: sends ~325MB to executor
# vs all 5 ABIs: would send ~560MB
ndk_cc_toolchain(
    name = "ndk_arm64",
    abi = "arm64-v8a",
    api_level = 21,
)

ndk_cc_toolchain(
    name = "ndk_x86_64",
    abi = "x86_64",
    api_level = 21,
)

# Build a native library — Buck2 only sends arm64 builtins + sysroot to executor
cxx_library(
    name = "mylib",
    srcs = ["jni/hello.cpp"],
    default_target_platform = "//platforms:android_arm64",
    deps = [],
)
```

### What Gets Sent to Each Executor

```
Executor receives (arm64-v8a build on Linux):
├── bin/clang, bin/ld.lld, bin/llvm-ar           # 204MB (executor-specific)
├── lib/clang/19/include/                         # 15MB  (builtin headers)
├── lib/clang/19/lib/linux/aarch64/               # 35MB  (THIS ABI only, not 370MB)
├── sysroot/usr/include/                          # 24MB  (all headers)
└── sysroot/usr/lib/aarch64-linux-android/21/     # 664KB (THIS ABI + API only)
                                            TOTAL: ~279MB

NOT sent (savings):
├── lib/clang/19/lib/linux/arm/                   # SKIPPED: 32MB
├── lib/clang/19/lib/linux/i386/                  # SKIPPED: 32MB
├── lib/clang/19/lib/linux/x86_64/                # SKIPPED: 33MB
├── lib/clang/19/lib/linux/riscv64/               # SKIPPED: 38MB
├── sysroot/usr/lib/arm-linux-androideabi/         # SKIPPED: 32MB
├── sysroot/usr/lib/i686-linux-android/            # SKIPPED: 33MB
├── sysroot/usr/lib/x86_64-linux-android/          # SKIPPED: 46MB
├── sysroot/usr/lib/riscv64-linux-android/         # SKIPPED: 74MB
├── bin/* (170+ unused tools)                      # SKIPPED: ~540MB
├── musl/, python3/, simpleperf/, shader-tools/    # SKIPPED: ~170MB
                                     NOT SENT: ~1.03GB
```

### Savings Table

| Configuration | Input to Executor | vs Full NDK (Linux 2.2GB) |
|---|---|---|
| All 5 ABIs (no slicing) | ~560MB | 4x reduction |
| 2 ABIs (arm64 + x86_64) | ~325MB | **6.8x reduction** |
| 1 ABI (arm64 only) | ~279MB | **7.9x reduction** |
| Full NDK (no extraction) | 2,200MB | baseline |

### What Buck2 Actually Needs (minimum viable slice)

For compiling + linking a `.so` for a single ABI on a single executor:

| Component | Required |
|---|---|
| `bin/clang-19` (or `clang.exe`) | YES |
| `bin/ld.lld` (or `ld.lld.exe`) | YES (invoked by clang) |
| `lib/clang/*/lib/linux/{abi}/` | YES (compiler builtins — **only for target ABI**) |
| `sysroot/usr/include/` | YES (all 24MB — not worth slicing, see below) |
| `sysroot/usr/lib/{triple}/{api}/` | YES (CRT + platform libs — **only for target ABI**) |
| `bin/llvm-strip` | RELEASE ONLY |
| `bin/llvm-objcopy` | DEBUG INFO ONLY |
| Everything else | NO |

---

## Minimum Input Size Per Executor

### Measured sizes (single ABI = arm64-v8a, API 21)

| Component | Linux | macOS | Windows | Shared? |
|---|---|---|---|---|
| `clang` (compiler) | 130MB | 165MB (universal) | 246MB (clang.exe + clang++.exe*) | per executor |
| `ld.lld` (linker) | 59MB | 111MB | 72MB | per executor |
| `llvm-ar` | 15MB | 26MB | 16MB | per executor |
| `llvm-strip` | 5.7MB | 8.9MB | 5.7MB | per executor |
| `llvm-objcopy` | 5.7MB | 8.9MB | 5.7MB | per executor |
| Compiler builtins (1 ABI) | 35MB | 35MB | 35MB | per target ABI |
| Builtin headers (`lib/clang/19/include/`) | 15MB | 15MB | 15MB | identical |
| Sysroot headers (`sysroot/usr/include/`) | 24MB | 24MB | 24MB | identical |
| Platform libs (1 ABI, 1 API level) | 664KB | 664KB | 664KB | identical |
| **MINIMUM TOTAL** | **~290MB** | **~395MB** | **~420MB** | |

*Windows: `clang.exe` and `clang++.exe` are **separate files** (different inodes, 123MB each — not symlinks). On Linux/macOS, `clang++` is a symlink to `clang` (0 bytes extra).

### Where the savings are: Drop unused ABI builtins

Compiler builtins (`lib/clang/19/lib/linux/{arch}/`) are **35MB per ABI** and the NDK ships all 5:

| ABI builtin dir | Size |
|---|---|
| `lib/clang/19/lib/linux/aarch64/` (arm64-v8a) | 35MB |
| `lib/clang/19/lib/linux/arm/` (armeabi-v7a) | 32MB |
| `lib/clang/19/lib/linux/i386/` (x86) | 32MB |
| `lib/clang/19/lib/linux/x86_64/` (x86_64) | 33MB |
| `lib/clang/19/lib/linux/riscv64/` (riscv64) | 38MB |
| **Total all ABIs** | **370MB** |

**If you only build for `arm64-v8a`: drop the other 4 ABI dirs and save ~135MB.**

Typical production setup (arm64-v8a + x86_64 for emulator): keep 2, drop 3, save ~102MB.

### Why NOT to slice headers

Sysroot headers are only 24MB total (6-8% of minimum input). Breakdown:

| Category | Size | Can skip? |
|---|---|---|
| C core (bits/, sys/, root .h, asm-generic/) | 6.2MB | NO — always needed |
| C++ libc++ (c++/v1/) | 9.5MB | Only if pure C |
| Linux kernel UAPI (linux/, drm/, sound/, etc.) | 5.4MB | NO — pulled transitively by C core |
| Android NDK APIs (android/, camera/, media/) | 2.3MB | Technically yes |
| Graphics (vulkan/, GLES*/, EGL/) | 2.0MB | Technically yes |
| Per-ABI asm headers (only need 1 of 5) | 180-344KB each | Save ~1MB |

Headers `#include` each other transitively. Slicing them saves ~13MB max (dropping C++, graphics, unused ABI asm) but creates a fragile build that breaks when code adds an `#include`. **Not worth the complexity for 3-4% of total input.**

### Per-ABI sysroot platform libs

These are also per-ABI but very small — not the bottleneck:

| ABI (all API levels) | Size |
|---|---|
| `aarch64-linux-android/` | 49MB |
| `arm-linux-androideabi/` | 32MB |
| `i686-linux-android/` | 33MB |
| `x86_64-linux-android/` | 46MB |
| `riscv64-linux-android/` | 74MB |
| **Total** | **232MB** |
| Single ABI, single API level | **~664KB** |

For a single API level build, you only need the specific `{triple}/{api}/` subdir (~664KB) plus the ABI-root STL lib. But these are shared across executors so the savings don't multiply.

### Summary: Practical minimum per executor

**Most common case:** CI on Linux, building arm64-v8a + x86_64:

| What to include | Size |
|---|---|
| `bin/clang`, `bin/ld.lld`, `bin/llvm-ar`, `bin/llvm-strip`, `bin/llvm-objcopy` | ~216MB |
| `lib/clang/19/include/` (builtin headers) | 15MB |
| `lib/clang/19/lib/linux/aarch64/` + `lib/clang/19/lib/linux/x86_64/` (2 ABIs only) | 68MB |
| `sysroot/usr/include/` (all headers) | 24MB |
| `sysroot/usr/lib/aarch64-linux-android/21/` + `sysroot/usr/lib/x86_64-linux-android/21/` | ~1.3MB |
| `build/cmake/android.toolchain.cmake` + `meta/abis.json` | <1MB |
| **TOTAL** | **~325MB** |

**vs full Linux NDK: 2.2GB (6.8x reduction)**

---

## Related Documentation

- **[BUCK2_ANDROID_SDK_EXTRACTIONS.md](./BUCK2_ANDROID_SDK_EXTRACTIONS.md)** - SDK extraction (Java/DEX tools)
- **[BUCK2_INTEGRATION.md](./BUCK2_INTEGRATION.md)** - Overall Buck2 + AGP architecture
