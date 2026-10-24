# Decision 0005: CLI-only keyword retrieval baseline

Status: experimental A-role backend increment on 2026-10-24. This is not a final search-quality claim.

- Search is available only through `python -m app.cli search`; no end-user HTTP search or answer endpoint is added yet.
- Candidate chunks come from one `kb_id`, active document versions, and the current chunking strategy. An unknown knowledge base is an error; a real no-match query returns an empty result.
- Tokenization uses lowercase ASCII words/numbers and overlapping Chinese character bigrams. Headings are included as metadata terms. This avoids an extra segmentation dependency but needs evaluation on real vocabulary.
- Ranking uses a smoothed positive-IDF BM25-style score with `k1=1.2` and `b=0.75`, limited to 1–20 results. Scores are **relative ranking values**, not probabilities or an automatic answer/refusal threshold.
- The corpus is read and scored in memory per query. This is acceptable for the first small test corpus, not a production indexing architecture.
- The web API's `searchable: false` remains unchanged: a CLI diagnostic search does not mean documents are indexed and ready for trustworthy end-user Q&A.

Next: build a small labeled question set and inspect misses/false matches before selecting a vector model, embedding API, or fusion approach. Any model/API choice and cost/privacy implications must be confirmed with the team.
