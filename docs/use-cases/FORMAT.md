# Use-Case Format

This file defines how to document use-cases in this catalog.

## Entry Format

```markdown
## [Use-Case Name]

**Problem:** What problem this solves. One or two sentences.

**Problem indicators:**
- "need to handle concurrent cache invalidation"
- "how do I prevent duplicate event processing"
- "cross-service retry with backoff"

**Location:** `src/path/file.ext:ClassName.methodName`

**Notes:** Implementation constraints, design trade-offs, why alternatives
were rejected. Be specific — mention concrete types, ordering constraints,
platform-specific behavior. Explain the "why", not the "what".
```

**Problem indicators** are short phrases (3-8 words) that a developer
or AI assistant would think or say when facing the same problem. They
are search terms, not descriptions. Start them with "need to...",
"how do I...", or a noun phrase like "cross-thread error counting".

**Location** includes both the file path and the symbol name. The file
path makes it immediately navigable; the symbol name survives minor
file reorganizations.

**Notes** should explain constraints and trade-offs, not restate what
the code does. If someone could understand it just by reading the code,
it doesn't belong in Notes.

## Cross-Domain References

When a use-case spans multiple domains, define it in one primary domain and add a cross-reference in related domains:

```markdown
## [Use-Case Name]

**See:** other-domain.md#use-case-name

**Problem indicators:**
- "phrase for searchability"
```

## When to Document

Document solutions that meet any of these criteria:

- **Non-obvious:** someone unfamiliar would likely reimplement differently
- **Reusable:** the pattern applies to future work, not just its current call site
- **Subtle:** the design has constraints or trade-offs not apparent from the code alone
- **Cross-cutting:** the solution spans multiple files or modules

## When NOT to Document

- Trivial CRUD, simple getters/setters, anything self-evident from reading the code
- One-off code unlikely to be reused
- Standard library/framework usage (put these in DEVELOPMENT.md under Patterns)
- Test files

## Domain Organization

Group use-cases by natural domain boundaries — modules that own a
coherent responsibility. Look at directory structure, module declarations,
and import graphs to identify domains. Aim for 3-8 use-cases per domain.
If a domain has more than 10, split it or raise the bar for inclusion.

## Maintenance

- Location fields must point to real files and symbols that exist in the codebase
- Include multiple problem indicators per use-case for searchability
- Problem indicators must be phrases someone would actually think before searching — not restated descriptions of the solution
