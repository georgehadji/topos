# Review of `INITIAL_PROMPT.md`

Verdict: strong *coverage*, weak *engineering*. It enumerates a wish-list but gives the
architect nothing to optimize against, so the output will be an unfalsifiable catalogue
rather than a design. Below: 15 defects, ranked by how much they degrade the result.

---

## CRITICAL

### C1. No constraints — the design is unfalsifiable
The prompt never states users, data volume, latency targets, budget, team size, or timeline.
Without those numbers every architecture is "correct", so the model defaults to the most
impressive-sounding one. A 5-person political office and a national agency get the same
answer, and only one of them is right.

**Fix:** a mandatory `PARAMETERS` block. Budget alone decides Kafka-vs-Postgres-queue,
Neo4j-vs-Postgres-recursive-CTE, and Kubernetes-vs-single-VM. See v2 §3.

### C2. "Do NOT optimize for simplicity" is an anti-instruction
It licenses gold-plating and removes the model's main quality signal. Real senior work is
*appropriate* complexity: every component earns its place against a stated requirement.
As written, the prompt guarantees an over-built system nobody can operate.

**Fix:** replace with a justification rule — each component must name the requirement it
serves and the simpler option it beats, plus a mandatory *rejected components* section. v2 §2.

### C3. The stack is pre-decided, so "recommend the optimal stack" is theatre
Kafka, Neo4j, Qdrant, OpenSearch, K8s, event sourcing + CQRS + saga + outbox are all named
in the requirements. The model will rationalize the list instead of choosing. Also: event
sourcing *and* CQRS *and* saga *and* outbox in one system is three distinct complexity taxes;
few teams under 20 engineers survive it.

**Fix:** move every product name into an "evaluate → adopt or reject with reason" table,
downstream of the requirements. v2 §11.

### C4. The Greek problem is never mentioned — and it is the whole technical risk
Target is Α΄ Θεσσαλονίκης. Greek OCR on scanned ΦΕΚ/ΚΗΜΔΗΣ PDFs, Greek NER, Greek diarized
STT, Greek embeddings, and Greek toponym resolution (`Τούμπα` vs `Άνω Τούμπα`, transliteration,
polytonic archives, genitive-case street names) are all materially worse than their English
equivalents. A design that assumes English-grade component accuracy is fiction, and every
downstream score inherits the error.

**Fix:** language handling promoted to a first-class subsystem with measured baselines and
a fallback ladder. v2 §5.

### C5. Legal exposure is waved away, not designed for
"Political Intelligence Platform" + campaign teams + person extraction + "publicly available
social media" is GDPR Art. 9 special-category processing (political opinions) plus, in most
cases, platform-ToS violation. One sentence saying "the goal is not voter profiling" is not a
control. Also unaddressed: EU AI Act classification, DPIA, lawful basis for citizen
submissions, defamation risk from AI-attributed blame to named officials.

**Fix:** non-negotiable constraint block *plus* a requirement to design the enforcement
mechanism (schema-level, not policy-level). v2 §4.

---

## HIGH

### H1. Scope is unachievable in one pass
11 modules × 16 dimensions + 28 agents × 8 dimensions + 25 deliverables ≈ 500 spec sections.
Any single response is uniformly shallow; "do not stop until every subsystem is fully
specified" fights the context budget rather than the problem.

**Fix:** staged workflow emitting files, with a gate between stages. v2 §7.

### H2. Self-review is scheduled where it cannot work
"Critically review, iterate once more" lands at the end of ~500 sections, at maximum fatigue.
It produces a polite paragraph of pseudo-criticism.

**Fix:** a separate red-team stage with an adversarial brief and pre-seeded failure
hypotheses the reviewer must confirm or refute with evidence. v2 §12.

### H3. No output contract
No file layout, no diagram format, no ADR convention, no length target. "C4 diagrams
(textual)" is worse than Mermaid, which renders everywhere and diffs cleanly in git.

**Fix:** explicit file tree, Mermaid, MADR-style ADRs. v2 §6.

### H4. Missing subsystems, several of them load-bearing
Absent from the original and hard to retrofit:
- **Entity resolution** — deduplicating the same pothole across 40 sources is the single
  hardest problem in the system and it is not listed.
- **Human-in-the-loop review queue** — required for any evidence claim, and required by EU AI Act.
- **Evaluation set / ground truth** — no way to know extraction quality without one.
- **Reprocessing & backfill** — swapping the extraction model invalidates years of derived
  facts; the migration path must exist from day one.
- **Source rights & licensing** — per-source terms determine what may be stored and shown.
- **Adversarial resistance** — astroturfing and brigading of the citizen channel is *certain*
  in a political product; the original treats submissions as trustworthy input.
- **Content moderation** — citizen uploads bring defamation, PII of third parties, and abuse.
- **Multi-tenancy** — a second constituency is the obvious next sale.
- **FinOps** — LLM spend per document is the dominant variable cost.

### H5. "Nothing should be a black box" contradicts the AI-first mandate
LLMs *are* black boxes. The reconcilable claim is that the *pipeline* is auditable: input
hash, prompt version, model version, parameters, raw output, citation offsets, reviewer.
Left unresolved, the model will emit hand-waving about "explainability".

**Fix:** state the distinction and require citation-offset-level provenance. v2 §9.

---

## MEDIUM

### M1. The 13 scores are not independent
Priority is a *function* of severity, impact, urgency, cost, and leverage — not a sibling.
Requesting 13 co-equal formulas invites double-counting and a weighted-sum with invented
constants that nobody can defend.

**Fix:** demand a DAG of scores, plus a sensitivity analysis and a calibration procedure. v2 §10.

### M2. 28 agents is an org chart, not an architecture
Most listed "agents" are deterministic pipeline stages (dedup, OCR, geocoding, alerting).
Wrapping them in LLM agents adds latency, cost, and non-determinism for no benefit.

**Fix:** require classification of each capability as deterministic / ML / LLM, with LLM use
justified. v2 §8.

### M3. Persona stacking and vendor-worship
Ten stacked job titles and "think like Palantir + Google + Stripe + OpenAI combined" bias
toward scale-cargo-culting. Those firms solve problems six orders of magnitude larger.

**Fix:** one role, plus explicit design values.

### M4. Deliverables are in the wrong order
Executive Summary first forces the summary before the analysis exists.

**Fix:** dependency-ordered stages; summary written last, placed first.

### M5. Duplication and drift
"Estimated Cost" appears in both Problem Engine and Intelligence Engine; Evidence Score and
Confidence Score appear in three places with no single owner.

**Fix:** single-owner rule per field, referenced elsewhere.

### M6. Formatting wastes ~65% of the tokens
1079 lines of blank-line-separated single words. It also destroys hierarchy: the model cannot
distinguish "this is a per-module template" from "this is a list of modules". v2 is ~40% the
size with strictly more information.

---

## Output

`INITIAL_PROMPT.v2.md` — rewritten prompt applying all of the above.
Fill the `PARAMETERS` block before running it; the defaults are guesses and are marked as such.
