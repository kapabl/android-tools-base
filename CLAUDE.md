# Claude Code Search Methodology

## Mandatory Search Tool Order

When searching this codebase, follow this strict hierarchy:

0. **zoxide** (`z`) - Navigate to directories (ALWAYS use before cd)
1. **fd** - Fast file/directory finding
2. **ast-grep** - AST-based structured code search
3. **ctags** - Symbol/definition lookup
4. **ripgrep (rg)** - Unstructured text search (fallback only)

**NEVER use `find` or `grep` commands.**
**NEVER use `cd` without first trying zoxide (`z`).**

## Navigation

- Use **zoxide** (`z`) for directory navigation
- Use **cd** only as a fallback when zoxide doesn't have the path indexed

### Index the repository with zoxide:
```bash
# Run this once to index all directories in the repo
find /home/kapablanka/repos/android-tools-base -type d -exec zoxide add {} \;

# Or use fd (preferred):
fd -t d . /home/kapablanka/repos/android-tools-base -x zoxide add {}
```

After indexing, navigate with:
```bash
z gradle-plugin    # Jump to gradle plugin directory
z build-system     # Jump to build system directory
z <partial-name>   # Fuzzy match to any indexed directory
```

## Search Strategy

- Start with **fd** for locating files by name/pattern
- Use **ast-grep** for structured code queries (class definitions, method signatures, imports, etc.)
- Use **ctags** for finding symbol definitions and references
- Only fall back to **ripgrep** when the above tools cannot find the target (unstructured text, comments, strings)

## Sub-Agent Requirements

When generating sub-agents, always pass this prompt to them:

```
Follow the mandatory search order: zoxide (z) -> fd -> ast-grep -> ctags -> ripgrep (unstructured text only).
Never use find or grep commands.
Never use cd without first trying zoxide (z).
When switching from ast-grep to rg, document the reason in your report.
```

## Reporting Requirements

At the end of each task and sub-agent execution, provide a report with:

```
Tools used: [list of tools]
False positives: [count]
Tokens used: [count]
Lines analyzed: [count]
Files processed: [count]
```

### When switching from ast-grep to ripgrep:
Document the reason explicitly:
```
Switched to ripgrep because: [reason - e.g., "searching for string literals in comments", "unstructured log messages", "documentation text"]
```

## Examples

### Good Search Flow
```bash
# 0. Navigate to directory
z gradle-plugin  # Use zoxide first

# 1. Find build-related files
fd -e gradle -e kt build

# 2. Search for AGP task definitions structurally
ast-grep --pattern 'class $NAME : DefaultTask'

# 3. Find symbol definitions
ctags -R --languages=Kotlin,Java

# 4. Only if needed: search unstructured content
rg "AGP pipeline" --type md
```

### Avoid
```bash
# ❌ DON'T USE
find . -name "*.gradle"
grep -r "AGP" .
```
