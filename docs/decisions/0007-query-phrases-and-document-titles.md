# Decision 0007: query phrases and exact document-title matches

Implemented 2026-11-10, following the user's request to fix the broad-query retrieval miss. This changes the existing local ranker, not the model, database schema, chunk boundaries or API fields.

The ranker now removes a small set of generic Chinese question phrases (`请问`, `如何/怎么` with an optional `管理/使用/操作`) from the ranking query. A query containing only those phrases falls back to its original text. Concrete operations such as deletion/export, negation, numbers and codes are retained. The original question still reaches the model and API response. The stored source text is never normalized this way.

We multiply a positive two-channel BM25 score by **2** when the complete top-level heading occurs in the ranking query. Titles shorter than two characters are ignored; ASCII word boundaries prevent `API` from matching inside `myapiclient`. This is a small structural prior, not a hard document filter. Neither product names nor fixture-specific topic words or filenames are encoded in the ranker. Scores remain relative ordering values, not confidence.

Controlled experiments on freshly imported public fixtures gave the following results:

- Original Agent Insight development questions: Top-1 **12/18 → 12/18**, Top-5 **17/18 → 17/18**; all 18 positive answer ranks stayed unchanged. All 5 unanswerable questions still have lexical hits.
- Fictional demo: Top-1 **10/12 → 10/12**, Top-5 **12/12 → 12/12**; all 12 positive answer ranks stayed unchanged. Its 4 negative questions still have hits.
- Separate diagnostic questions: Top-1 **1/3 → 1/3**, Top-5 **1/3 → 3/3**. B01 moves from missing to rank 2; B02 moves from missing to rank 4; B03 remains rank 1.

Rejected alternatives: adding a separate BM25 score over all heading terms reduced Agent Insight Top-1 to 8/18 at weight 1; merely removing `如何/怎么/请问` did not improve the three diagnostic ranks; title boosting alone did not recover both misses. A title multiplier of 2 was the smallest tested multiplier that recovered B01 when combined with generic-phrase cleanup. These choices were tuned on known development questions; the diagnostics are not an independent holdout.

Regression coverage includes the original datasets, the three diagnosed queries, synthetic appointment questions in another domain, exact source offsets, codes/negation, title boundaries, and an HTTP answer test that confirms the experiment entry reaches a simulated model with the original question intact. This does not establish real-model answer quality. No paid calls were made for these experiments.

Remaining limitations: B01/B02 are not rank 1; one original positive case remains outside Top-5; lexical matches still cannot prove answer support. The phrase rules do not cover arbitrary paraphrases. Independent questions and human review remain necessary before claiming broad quality improvement.
