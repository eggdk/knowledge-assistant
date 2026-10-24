# Decision 0004: traceable MD/TXT chunks

Status: first backend implementation on 2026-10-24. Parameters are experimental; review them against a small evaluation set before claiming retrieval quality.

- Strategy ID is `mdtxt-v1`. Current starting values: maximum 600 characters, minimum breakpoint search at 250 characters, and 80-character overlap for long sections. Short heading sections may be much smaller.
- Markdown heading hierarchy is recorded as metadata. Heading-like lines inside fenced code blocks do not create sections. TXT is treated as one section.
- Prefer paragraph boundaries, then sentence punctuation, then line boundaries; hard-cut only when necessary. Chunk text is an exact slice of normalized parsed text, with character offsets and line ranges for later citation checks.
- Each chunk has `kb_id`, document ID, document version, chunk ordinal, strategy version, content hash, and a deterministic chunk ID. The schema is additive for older local SQLite files.
- Import writes a new document version and all of its chunks in one database transaction; a chunk-write failure cannot activate a partial version. Re-importing unchanged older documents fills missing chunks without making a fake new document version.
- Active-chunk queries filter by both active document version and current strategy. Old chunks remain for version history but are not current retrieval candidates.

This is **not** a search index and does not make documents answerable. `searchable: false` in the HTTP API remains correct. The next retrieval stage needs a measured baseline, knowledge-base filtering, and evidence-based citation behavior. Word/Excel/PDF will require format-specific locations rather than pretending every source has simple text line numbers.
