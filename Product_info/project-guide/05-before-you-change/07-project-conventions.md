# Before Changing Project Conventions

> **Purpose:** Preserve repository-wide engineering decisions and documentation alignment.
> **Read this before:** Adding dependencies, reorganizing modules, changing error policy, or committing work.
> **Source files:** `CLAUDE.md:3`, `requirements/`, `Makefile`, `ARCHITECTURE.md`

## What breaks easily here, and why

The project intentionally avoids backward-compatibility shims, uses a strict error
policy, and requires docs to move with code. Adding a second package manager,
duplicated module boundary, or broad exception handling creates long-term drift.

## Required steps

1. Follow existing module ownership and import direction.
2. Add direct dependencies to the appropriate `requirements/*.txt` file.
3. Use expected-error handling only; allow unexpected failures to surface.
4. Update `CLAUDE.md`, `ARCHITECTURE.md`, and this guide with behavior changes.
5. Keep commits single-line with no `Co-Authored-By` footer when committing is requested.

## Cross-cutting rules

- no auto-memory files; durable project knowledge belongs in checked-in docs;
- no compatibility wrappers for obsolete internal Python APIs;
- migrations remain compatible with existing databases;
- shared logic belongs in domain services, not duplicated in views/tasks;
- preserve unrelated user changes in the working tree.

## If you change A, you must also update B

- dependency → local and production requirement chains, Docker build, imports, tests;
- module path → all callers, tests, architecture map; remove old path rather than shim;
- exception policy → callers and failure-state UI;
- command/startup flow → README, Makefile/scripts, managed deployment docs;
- architecture rule → CLAUDE, ARCHITECTURE, and relevant project-guide section.

## Tests that must pass

```powershell
uv run --no-sync python manage.py check
uv run --no-sync pytest
```

Also inspect `git diff --check` and the final file list for unintended generated or
secret files before committing.

