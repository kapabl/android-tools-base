#!/usr/bin/env python3
"""
Generate Buck2 targets for Android app compilation and dexing.

Reads AGP build model (from init-extract-model.gradle) and generates:
1. Dependency extraction target (gradle-based)
2. Java/Kotlin compilation target (java_library)
3. Android DEX target (android_dex custom rule)

Usage:
    python3 generate-android-build-targets.py path/to/agp-build-model.json > BUCK
"""

import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("Usage: generate-android-build-targets.py <agp-build-model.json>", file=sys.stderr)
        sys.exit(1)

    model_path = Path(sys.argv[1])
    if not model_path.exists():
        print(f"Error: {model_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(model_path) as f:
        model = json.load(f)

    # Use first variant (debug/release/etc)
    variant_name = list(model.keys())[0]
    variant = model[variant_name]

    print(f"# Generated Buck2 targets from AGP build model")
    print(f"# Variant: {variant_name}")
    print(f"# Source: {model_path}")
    print()

    # Gradle deps extraction (calls gradle to download all dependencies)
    print("gradle_deps(")
    print("    name = \"deps\",")
    print("    gradle_files = \"//:gradle_config_files\",")
    print(")")
    print()

    # Generate java_library for compilation
    has_kotlin = variant.get('hasKotlin', False)

    print("java_library(")
    print("    name = \"app_classes\",")
    print("    srcs = [")
    print("        \"//:app_java_sources\",")
    if has_kotlin:
        print("        \"//:app_kotlin_sources\",")
    print("        \"//:app_generated_sources\",")
    print("    ],")
    print("    deps = [\":deps\"],")

    # Add source/target compatibility if available
    if 'sourceCompatibility' in variant:
        print(f"    source = \"{variant['sourceCompatibility']}\",")
    if 'targetCompatibility' in variant:
        print(f"    target = \"{variant['targetCompatibility']}\",")

    print(")")
    print()

    # Generate android_dex target
    print("android_dex(")
    print("    name = \"app_dex\",")
    print("    classes = [\":app_classes\"],")
    print("    deps = [\":deps\"],")

    # SDK versions
    print("    d8_version = \"33.0.0\",")
    if 'compileSdkVersion' in variant:
        # Extract numeric version from compileSdkVersion (e.g., "android-33" -> "33")
        compile_sdk = str(variant['compileSdkVersion']).replace('android-', '').replace('Android ', '')
        print(f"    platform_version = \"{compile_sdk}\",")
    else:
        print("    platform_version = \"33\",")

    # Min SDK (mandatory)
    if 'minSdkVersion' in variant:
        print(f"    min_sdk = {variant['minSdkVersion']},")
    else:
        print("    min_sdk = 21,  # Default")

    # Multi-dex
    if variant.get('multiDexEnabled', False):
        print("    multi_dex = True,")
    else:
        print("    multi_dex = False,")

    # Debug mode
    if 'debuggable' in variant:
        print(f"    debug = {str(variant['debuggable']).lower()},")
    else:
        print("    debug = False,")

    # Desugaring (enabled by default)
    print("    enable_desugaring = True,")

    print(")")
    print()

    # Print summary of what was found
    print("# Build model summary:")
    print(f"#   Variant: {variant_name}")
    print(f"#   Has Kotlin: {has_kotlin}")
    print(f"#   Compile dependencies: {len(variant.get('compileClasspath', []))}")
    print(f"#   Runtime dependencies: {len(variant.get('runtimeClasspath', []))}")
    print(f"#   Annotation processors: {len(variant.get('annotationProcessors', []))}")
    if variant.get('kaptDependencies'):
        print(f"#   KAPT dependencies: {len(variant['kaptDependencies'])}")
    if variant.get('multiDexEnabled'):
        print("#   Multi-DEX: enabled")


if __name__ == "__main__":
    main()
