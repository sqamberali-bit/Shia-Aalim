# Hallucination prevention

Preventing fabrication is the project's first requirement. The charter lists
eight controls; this document maps each to where it lives in the codebase and
how it behaves.

| Charter control | Where | Behaviour |
|---|---|---|
| Multi-source retrieval | `retrieval/retriever.py` | over-sample then re-rank; `consensus()` groups by source |
| Source consensus verification | `retriever.consensus()` | reports how many *distinct* sources support a point |
| Retrieval confidence scoring | `retriever.retrieve()` | confidence-aware re-rank; unverified content demoted |
| Citation validation | `grounding/verify.py::validate_citations` | completeness + source-exists + passage-exists |
| Query decomposition | (hook) | decompose complex questions before retrieval (LLM step) |
| Answer grounding checks | `grounding/verify.py::check_answer_grounding` | each claim must overlap retrieved evidence |
| Post-generation fact verification | `generation/answer.py` | synthesizer output re-run through grounding |
| Source existence verification | `grounding/verify.py` | citations to unregistered sources are rejected |

## The firewall, in order

1. **Similarity floor.** A passage only weakly similar to the question is not
   evidence *for* it. If nothing clears the floor (default `0.15`), the system
   **refuses to answer** rather than reaching. Without this, extractive answers
   would trivially "ground" against whatever the index returned.
2. **Source existence.** Every citation's `source_id` must be in
   `registry.yaml`. An invented book is caught here.
3. **Citation completeness.** Qurʾān needs sūra+āya; hadith needs a locator;
   tafsīr/scholarly need a volume/page/chapter. Incomplete citations cannot be
   asserted as fact.
4. **Passage existence.** When the corpus is available, the cited locator is
   checked against ingested documents — an invented volume/page is caught.
5. **Answer grounding.** Each claim's text must materially overlap some
   retrieved passage. The lexical check is conservative (it can flag but should
   be *complemented* by an LLM entailment check — never replaced by one).
6. **Fact/hedge consistency.** Nothing is asserted as established unless its
   confidence and citations permit it (`Claim.can_state_as_fact`).

## Why extractive-by-default

In the default configuration the answer generator returns **verbatim cited
passages**, not original prose. It literally cannot hallucinate content because
it never writes a novel sentence. Fluency (an LLM `Synthesizer`) is an explicit
upgrade — and even then the output passes back through steps 2–6 before release,
with a caveat attached if grounding raises warnings.

## Honest limitations

- Lexical overlap is not semantic entailment: a paraphrase may score low, and an
  unrelated sentence sharing tokens may score high. Add an LLM entailment judge
  for production; the interface already re-verifies synthesizer output.
- The `HashingEmbedder` is a baseline; retrieval quality (and thus grounding
  input) improves substantially with a semantic model — measured via
  `evaluation/`.
- Passage-existence checking is only as complete as the ingested corpus.
