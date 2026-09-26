# linkreach Project Guide

> **Purpose:** Provide a source-grounded map of linkreach and the checks required before changing it.
> **Read this before:** Any feature, refactor, schema change, integration, or UI change.
> **Source files:** `CLAUDE.md`, `ARCHITECTURE.md`, `linkreach/`, `tests/`, `requirements/`

This guide describes the repository as it exists now. `CLAUDE.md` and
`ARCHITECTURE.md` define project intent; source code and migrations confirm the
implemented behavior. Where those disagree, the guide labels the mismatch rather
than silently choosing one.

## Suggested reading order

1. [Product overview](00-overview/README.md)
2. [Glossary](06-glossary/README.md)
3. [Architecture](01-architecture/README.md)
4. [Data and state](02-data-and-state/README.md)
5. [Intercommunication](03-intercommunication/README.md)
6. [Frontend and UI](04-frontend-and-ui/README.md)
7. [Before you change anything](05-before-you-change/README.md)

## Section index

- [`00-overview/`](00-overview/README.md) — product, users, mental model, and system diagram.
- [`01-architecture/`](01-architecture/README.md) — modules, runtime boundaries, integrations, security, and deployment modes.
- [`02-data-and-state/`](02-data-and-state/README.md) — models, lifecycles, writers, cascades, and retained data.
- [`03-intercommunication/`](03-intercommunication/README.md) — web requests, workers, polling, subprocesses, and environment handoff.
- [`04-frontend-and-ui/`](04-frontend-and-ui/README.md) — templates, design system, HTMX behavior, pages, and known traps.
- [`05-before-you-change/`](05-before-you-change/README.md) — mandatory change-safety checklists and verification commands.
- [`06-glossary/`](06-glossary/README.md) — domain language, schema names, processes, and acronyms.

## Authority and maintenance

- Update this guide in the same change as behavior it describes.
- Database changes require migrations even though Python API compatibility is not required.
- Treat credentials, cookies, email addresses, and conversation content as sensitive.
- Do not infer multi-tenant isolation: the current dashboard is login-protected but many queries are global.
- Prefix uncertain claims with `UNVERIFIED:` and name the missing evidence.

