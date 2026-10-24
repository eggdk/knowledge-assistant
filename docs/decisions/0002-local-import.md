# Decision 0002: first local document import

Status: confirmed by the A-role student on 2026-10-21. This is a team design choice, not a literal course requirement.

## Decision

- The first import stage supports UTF-8 `.md` and `.txt` files (UTF-8 BOM accepted). Word/Excel/PDF come later.
- A knowledge base is identified by `kb_id`. Within it, a document is identified by the selected folder's relative path. Moving/renaming a file currently creates a new document; the old one is not implicitly deleted.
- Exact original bytes are retained by default inside SQLite, together with parsed text, source path, SHA-256, import time, and numbered versions. `--originals skip` is an explicit exception for special imports.
- Same bytes at the same path do not create a new version. Changed bytes create a new version and only a successful parse makes it active. A bad update leaves the old active version intact.
- Missing files in a later import never mean deletion. Explicit deletion and full-directory synchronization will be separate features with preview/confirmation.
- Both CLI and future HTTP upload should call the same parser and store functions. The current CLI scans only a directory the operator explicitly passes.

## Why

Keeping a byte-for-byte original makes later citation inspection and parser debugging possible even after a source file changes. SQLite is sufficient for the first small MD/TXT stage and keeps team setup simple. The tradeoff is a larger local database; large-file limits and dedicated object storage can be revisited when multi-format import arrives.

This decision does not claim that retrieval, answer generation, source citations, browser upload, or Agent Insight integration is already working.
