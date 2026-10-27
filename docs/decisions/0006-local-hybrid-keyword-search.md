# Decision 0006: local two-channel keyword search

Status: experimental CLI-only backend increment, 2026-10-27.

The user chose to improve local retrieval before adding a vector model or answer API. We preserve the original Chinese overlapping-bigram BM25 channel and add a second BM25 channel using `jieba.cut_for_search` word segments. Latin words and codes are case-folded in both channels. Each channel uses the same active chunks, heading metadata, positive-IDF BM25 parameters (`k1=1.2`, `b=0.75`), and its own document-frequency statistics. We add the two ranking scores with equal weight. They remain **relative ranks, not confidence values**.

The stored MD/TXT source, offsets, line ranges, version filtering, and knowledge-base isolation are unchanged. This is still an in-memory calculation for a small local corpus; no user-facing HTTP answer or search API is introduced. `jieba==0.42.1` is pinned in `apps/api/requirements.txt`; it runs locally and makes no model-service call. The upstream [jieba search-mode documentation](https://github.com/fxsjy/jieba) describes segmenting long words into additional shorter words for search.

The fixed 2026-10-27 development set in `evals/agent_insight` has 18 answerable and 5 unanswered questions. Against the previous bigram-only baseline, answer-bearing chunk Top-1 changed **9/18 → 12/18**, Top-5 stayed **17/18**, and negative questions with no lexical hit stayed **0/5**. The fictional demo set stayed **10/12 Top-1 and 12/12 Top-5**. Rank changes are mixed: T06, D05, and E02 reached rank 1, while E01 moved from rank 2 to rank 3. D02 remains outside Top-5.

We also tried markup-only removal and replacing bigrams entirely with jieba. Both produced 8/18 Top-1 on the real-document set, so neither was retained. This is a small team-authored development set, not a held-out quality estimate. Future retrieval changes should be compared on additional, independently reviewed questions before asserting general improvement. The five unanswerable questions still return lexical matches; answer support and refusal require a later evidence-checking step.
