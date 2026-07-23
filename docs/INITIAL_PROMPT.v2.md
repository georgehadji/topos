# Topos — Architecture Brief

> Rewrite of `INITIAL_PROMPT.md`. Rationale for every change: `PROMPT_REVIEW.md`.
> **Edit §3 PARAMETERS before running.** The values there are guesses and the design is
> worthless if they are wrong.

---

## 1. Mission

Design and specify a production system that continuously discovers, verifies, prioritizes and
explains the problems affecting citizens of a single Greek electoral constituency
(reference target: **Α΄ Θεσσαλονίκης**).

Users are a policy office: the elected official, 2–4 advisors, a researcher, a communications
lead. The product gives them defensible situational awareness — *what is wrong, where, since
when, who is responsible, how sure are we, and what has been tried.*

The chain is `raw data → information → knowledge → evidence → intelligence → recommendation`.
Every link must be traversable in both directions: from any rendered claim back to a byte
range in a source artifact, and from any source forward to everything derived from it.

**Out of scope, permanently:** voter profiling, persuasion targeting, sentiment analysis of
identifiable private individuals, opposition research on persons.

---

## 2. How to work

1. **Requirements first, products second.** Do not name a database, broker or framework until
   the requirement forcing it is written down with a number attached.
2. **Justify complexity.** Every component states (a) the requirement it serves, (b) the
   simpler alternative it beats, (c) what breaks if you delete it. Components failing this
   test go in the **Rejected** section — which is a required deliverable, not optional.
3. **Simplicity is the tiebreaker, not the goal.** Where two designs meet the constraints in
   §3, pick the one the stated team can operate at 3am. Correctness under constraint outranks
   elegance; elegance outranks completeness.
4. **Quantify or qualify.** Any unsupported number must be labelled `[ESTIMATE]` with its
   derivation. Any assumption must be labelled `[ASSUMPTION]` and listed in the assumptions
   register.
5. **Challenge the brief.** This document contains mistakes. Where a requirement is wrong,
   contradictory, or gold-plated, say so and propose the replacement. Silent compliance is a
   failure mode.
6. **No vendor cosplay.** Do not design for Palantir's scale. Design for §3's scale, with a
   named migration path to 10× that.
7. **Cite your own claims.** Any statement about a tool's capability, a Greek data source, or
   a model's accuracy must be marked `[VERIFIED]` (with URL) or `[UNVERIFIED]`.

---

## 3. PARAMETERS  ← *fill these in*

Defaults below describe a small, well-funded policy office. They are `[ASSUMPTION]`s.
If a parameter is wrong, the resulting architecture is wrong. Challenge any that seem
inconsistent before designing.

| Parameter | Default | Notes |
|---|---|---|
| Jurisdiction | Greece / EU | GDPR, EU AI Act, Greek public-sector data law |
| Constituencies at launch | 1 (Α΄ Θεσσαλονίκης) | Multi-tenant by year 2 |
| Population covered | ~700,000 | |
| Named users | 8 internal, 30 read-only stakeholders | Not a consumer product |
| Citizen submitters | 0 at MVP → 5,000 MAU by year 2 | Public-facing channel is a Phase-3 risk |
| New documents/day | 300–1,500 (bursty; council-session spikes ~10×) | |
| Historical backfill | ~5 years, ~500k documents | Dominates initial cost |
| Media/day | ~4 h audio (council sessions), ~200 images | |
| Corpus at year 2 | ~2 TB raw, ~50 M text chunks | |
| Query latency p95 | 2 s search, 10 s for a grounded synthesized answer | |
| Freshness SLO | breaking news ≤ 30 min; official gazettes ≤ 6 h | |
| Availability | 99.5% business hours; no on-call rota | Rules out designs needing 24/7 ops |
| Infra budget | €1,500–3,000 / month steady state | |
| LLM budget | €800 / month steady state, €5,000 one-off backfill | Hard ceiling; design to it |
| Team | 3 engineers + 1 part-time ML + 1 domain analyst | **No dedicated SRE, no DBA** |
| Timeline to first useful output | 10 weeks | |
| Primary language | Greek; English secondary | See §5 |
| Data residency | EU only | |

**Derived rule:** with 3 engineers and no SRE, any design requiring a managed Kubernetes
control plane, a self-hosted Kafka cluster, *and* a self-hosted graph database is
disqualified on operability grounds unless you argue the case explicitly.

---

## 4. Hard constraints (non-negotiable)

These are product constraints, not aspirations. Design the **mechanism** that enforces each —
a policy statement in a doc is not an answer.

| # | Constraint | Required mechanism |
|---|---|---|
| L1 | No profile of any natural person may be built or queryable | Schema-level: no `person` entity with aggregatable attributes; persons appear only as *role-bearing* references (`Mayor of X`, `Deputy Minister of Y`) bound to an office, not an individual dossier |
| L2 | No inference of political opinion, religion, health, ethnicity, or union membership of individuals | GDPR Art. 9. Extraction schema must make these fields unrepresentable |
| L3 | Social media only via ToS-compliant official APIs, or not at all | No scraping. Treat as an optional, degradable source; the design must work with it absent |
| L4 | Citizen submissions: explicit consent, purpose limitation, withdrawal, erasure | Erasure must propagate to derived facts, embeddings, and the graph — design this, it is hard |
| L5 | Every published claim carries a citation resolvable to a source byte range | See §9 |
| L6 | Recommendations affecting individuals or benefits require human sign-off before export | EU AI Act; audit-logged approval |
| L7 | Named officials may be linked to problems only via documented official responsibility | Blame attribution is a defamation vector; require a source establishing jurisdiction |
| L8 | EU data residency; encrypted at rest and in transit; keys not held by processors outside EU | |
| L9 | DPIA completed before public launch | Deliverable, not an afterthought |
| L10 | Source rights tracked per source; storage and redistribution honour them | Some Greek portals permit access but not redistribution |

---

## 5. Language and locale (first-class subsystem)

The dominant technical risk. Design explicitly; do not assume English-grade accuracy.

**Required analysis for each of OCR, NER, STT, embedding, summarization:**
measured Greek baseline (or `[UNVERIFIED]`), failure modes, fallback ladder, cost per unit,
and the human-review trigger threshold.

Known-hard cases that must be addressed:

- **Scanned ΦΕΚ / older municipal PDFs** — poor scans, two-column layout, tables, stamps.
  Generic Tesseract `ell` is inadequate; evaluate layout-aware OCR and commercial document AI,
  and price both against §3's budget.
- **Polytonic and pre-1982 orthography** in historical archives.
- **Toponym resolution** — `Τούμπα` / `Άνω Τούμπα` / `Κάτω Τούμπα`, informal neighbourhood names
  with no official boundary, street names in the genitive (`οδός Εγνατίας` → `Εγνατία`),
  Latin transliteration variants, and the same street name in multiple municipalities.
- **Greek NER** — off-the-shelf models under-perform on public-administration entities
  (ΟΤΑ, ΔΕΥΑ, ΚΗΜΔΗΣ identifiers, ΑΔΑ codes). Plan for a gazetteer + rules hybrid.
- **Diarized Greek STT** on council recordings with crosstalk, poor mics, and dialect.
- **Legal/administrative register** — decisions are written in a formal register far from the
  news text most models are tuned on.
- **Retrieval** — decide per-stage whether to embed Greek natively or pivot through English,
  and prove the choice with a retrieval eval on Greek queries.

**Deliverable:** a language-risk register with, per stage, `expected accuracy → downstream
consequence → mitigation → residual risk`.

---

## 6. Output contract

Emit files. Do not answer in one message.

```
docs/
  00-executive-summary.md          # written LAST
  01-context-and-constraints.md    # incl. assumptions register
  10-architecture-overview.md      # C4 L1–L2 as Mermaid
  11-data-flow.md
  12-event-flow.md
  2x-<subsystem>.md                # one per subsystem, §8 template
  30-data-model.md                 # DDL, with indexes and retention
  31-ontology.md                   # knowledge graph
  40-api.md                        # OpenAPI 3.1 + GraphQL SDL fragments
  50-ai-architecture.md
  51-evaluation.md                 # eval sets, metrics, gates
  60-security.md                   # incl. threat model + DPIA outline
  61-observability.md
  70-deployment.md                 # IaC shape, environments, DR
  80-roadmap.md                    # phases, team, risk register
  90-rejected.md                   # what was considered and dropped, and why
  91-open-questions.md
  adr/NNNN-<slug>.md               # one per irreversible decision
  99-red-team.md                   # §12
```

Rules:
- **Diagrams:** Mermaid only (`flowchart`, `sequenceDiagram`, `erDiagram`, `stateDiagram-v2`).
  Must render. No ASCII art.
- **Decisions:** MADR format — Context / Options / Decision / Consequences / Reversibility.
  An ADR is required whenever the decision is expensive to reverse.
- **Schemas:** real DDL (PostgreSQL dialect), not prose.
- **APIs:** real OpenAPI/SDL fragments for the 8 most important operations, prose for the rest.
- **Density:** no filler. A section that restates its heading is deleted.
- **Every subsystem doc ends with:** `Failure modes` table (`failure → detection → blast
  radius → recovery → residual risk`).

---

## 7. Work plan

Run in stages. **Stop at each `GATE` and report** before continuing.

| Stage | Produces | Gate |
|---|---|---|
| S0 | Constraint validation: which §3 parameters are internally inconsistent or implausible; what is missing | List questions and proceed with `[ASSUMPTION]`s |
| S1 | `01`, domain model, bounded contexts, the 3–5 hardest problems in this system named explicitly | **GATE:** confirm the hard problems before designing around them |
| S2 | `10`,`11`,`12`, ADRs for the top decisions, `90-rejected` | **GATE:** confirm shape and stack |
| S3 | `2x-*` subsystem specs, `30`,`31` | |
| S4 | `40`,`50`,`51` | |
| S5 | `60`,`61`,`70` | |
| S6 | `80` roadmap, cost model | |
| S7 | `99-red-team` (§12), then apply fixes, then `00-executive-summary` | |

Phasing rule for the roadmap: **Phase 1 must be shippable by 3 engineers in 10 weeks** and must
deliver standalone value with *zero* AI agents if necessary. If the design cannot degrade to
that, it is wrong.

---

## 8. Subsystems

### Per-subsystem template (apply to each; omit sections that are genuinely N/A, and say why)

`Purpose` · `Responsibilities` · `Non-responsibilities` · `Inputs` · `Outputs` ·
`Interfaces (API/events)` · `Data owned` · `Dependencies` · `Failure modes table` ·
`Consistency & idempotency` · `Scaling limits (first bottleneck + at what load)` ·
`Caching & invalidation` · `Security & authz` · `Observability (SLI, alerts)` ·
`Testing strategy` · `Cost per unit of work` · `Extensibility seam` · `Kill criteria`

### 8.1 Ingestion

1. **Source Registry** — every source as a declarative, versioned record: endpoint, auth,
   cadence, parser plugin, jurisdiction, **rights/licence**, reliability prior, health.
   Plugin contract must let the domain analyst add a source without an engineer.
2. **Collectors** — scheduling, backoff, rate limits, conditional fetch, content-hash dedup,
   incremental cursors, DLQ, and **change detection for silently edited or deleted sources**
   (public bodies edit documents in place; this must be captured as a versioned diff).
3. **Document Repository** — immutable blob store, content-addressed; metadata, versions,
   hashes, MIME, language, OCR state, rights, retention class. Evidence integrity implies
   **WORM semantics for anything ever cited**.

**Greek source starter set** (verify each, record licence and robots/ToS):
Διαύγεια (diavgeia.gov.gr) · ΚΗΜΔΗΣ/ΕΣΗΔΗΣ procurement · ΦΕΚ (et.gr) ·
Βουλή των Ελλήνων · Συνήγορος του Πολίτη · data.gov.gr · geodata.gov.gr ·
ΕΛΣΤΑΤ · Δήμος Θεσσαλονίκης + περιφερειακοί δήμοι · Περιφέρεια Κεντρικής Μακεδονίας ·
ΟΑΣΘ / ΟΣΕΘ · ΕΥΑΘ · ΔΕΔΔΗΕ outage feeds · Κτηματολόγιο · Copernicus / Sentinel ·
air-quality and meteo networks · local press · council minutes and recordings.

### 8.2 Understanding

4. **Document Processing** — OCR, layout reconstruction, table extraction, structure-aware
   chunking. LLM correction only where measured to help; prove it does.
5. **Speech** — STT, diarization, speaker attribution to *office* not person where possible,
   alignment of transcript spans to audio timecodes (needed for citation).
6. **Extraction** — structured output against a strict schema. Extract: problem statement,
   location, responsible authority, requested action, dates, affected infrastructure,
   quantities, cited legal references, confidence, **and the source span for each field**.
   Fields forbidden by L2 must be absent from the schema, not filtered afterwards.
7. **Geocoding** — address/landmark/neighbourhood → coordinates → administrative,
   electoral and statistical geographies. Must return calibrated uncertainty, not a point.
   PostGIS.
8. **Entity Resolution** ← *the hardest subsystem; do not under-specify.*
   The same problem appears in a news item, a council minute, a citizen report and a
   procurement notice, in different words. Specify blocking strategy, similarity features
   (text, geo, temporal, authority), the merge/split model, **reversible merges**, and the
   human adjudication queue. Getting this wrong destroys every count, trend and score.

### 8.3 Knowledge

9. **Knowledge Graph** — ontology over Problem, Location, Authority (office, not person),
   Infrastructure, Project, Budget line, Legal instrument, Document, Meeting, Event, Time.
   Define each relationship's cardinality, temporal validity, and provenance edge.
   Justify a dedicated graph store against Postgres + recursive CTEs at §3 scale.
10. **Problem Engine** — lifecycle state machine, not a record: `candidate → corroborated →
    verified → tracked → acted-upon → resolved → recurring`. Specify who or what advances
    each transition and what evidence is required.
11. **Constituency Model** — districts, neighbourhoods, facilities, transport, aggregated
    demographics (k-anonymity floor stated explicitly).
12. **GIS** — layers, tiling, projection (GGRS87/EPSG:2100 vs WGS84 — state the choice),
    rendering budget, and how uncertainty is drawn on a map without lying to the viewer.

### 8.4 Reasoning

13. **Evidence Engine** — §9.
14. **Intelligence / Scoring** — §10.
15. **Recommendation Engine** — interventions, legal instruments, funding programmes
    (ΕΣΠΑ / Ταμείο Ανάκαμψης / municipal budget lines), comparable precedents, expected
    impact, risks, success metrics. Every recommendation cites evidence and states what would
    falsify it. **Human approval gate before any export.**
16. **Search** — hybrid lexical + vector + graph + geospatial + temporal, with Greek-specific
    analysis (stemming, accent folding, compound handling) and a documented fusion strategy.
17. **Human Review & Feedback** — the annotation queue, adjudication UI, reviewer agreement
    tracking, and the loop that turns corrections into eval data. Load-bearing for L6 and §11.
18. **Reprocessing** — when an extraction model changes, how do 500k documents get
    re-derived without invalidating live citations or blowing the LLM budget? Specify
    versioned derivations, shadow runs, and diff review.

### 8.5 Delivery

19. **API** — REST + GraphQL + streaming + webhooks + MCP server; authn/z, quotas, versioning.
20. **Dashboard** — see §13.
21. **Citizen channel** — mobile/PWA submissions with offline capture, status tracking, and
    **abuse resistance** (§14).

---

## 9. Evidence and provenance

Resolve the contradiction in the original brief up front: **an LLM is a black box; the
pipeline around it must not be.**

Required for every derived claim:
- source document id + version + **byte/character offsets** (or audio timecodes)
- extraction run id → prompt version, model id, parameters, timestamp, cost
- corroboration set: independent sources supporting it, with independence actually tested
  (three outlets republishing one wire story is one source, not three)
- contradicting evidence, surfaced not suppressed
- reliability prior of each source, and how it is updated
- confidence, with a stated meaning and a calibration procedure
- review state and reviewer identity where human-adjudicated
- full history: claims strengthen, weaken and get retracted over time

Design the **retraction path**: when a source is corrected or withdrawn, everything derived
from it must be re-evaluated and any published artifact flagged.

---

## 10. Scoring

The original brief lists 13 co-equal scores. They are not co-equal — Priority is a *function*
of the others. Required:

1. A **DAG** of scores: leaves are measured or extracted quantities; internal nodes are
   defined combinations. No score may take another as input while also feeding it.
2. For each: definition, unit, range, inputs, formula, **worked example on a realistic case**,
   and its degradation behaviour under missing inputs.
3. **Sensitivity analysis** — which weights actually move the ranking. If a weight does not
   change the top 20, delete it.
4. **Calibration** — how weights are set, by whom, and how they are validated against expert
   ranking. Weights invented by the model must be labelled `[UNCALIBRATED]`.
5. **Gaming resistance** — a coordinated submission campaign must not move Priority. State
   how.
6. **User-facing explanation** — one sentence per score, in Greek, that a non-technical
   advisor understands.

Recommended reduction: measure `severity`, `reach`, `trend`, `evidence strength`,
`tractability`, `cost`; derive everything else. Argue for or against this.

---

## 11. AI architecture

- **Classify every capability** as `deterministic` / `classical ML` / `LLM`. Default to the
  cheapest tier that meets the accuracy bar. Deduplication, geocoding, alerting and routing
  are *not* LLM problems; if you make them LLM problems, justify it with numbers.
- **The 28 "agents" in the original brief are mostly pipeline stages.** Propose the minimum
  set of genuinely agentic components — those needing planning, tool selection, or iterative
  refinement — and implement the rest as deterministic steps. Justify each survivor.
- **Routing** — model tiers by task, with cost/latency/accuracy per tier, and a hard budget
  ceiling with graceful degradation (§3: €800/month is a real constraint).
- **Grounding** — retrieval strategy, context assembly, citation enforcement, and refusal
  when evidence is insufficient. "No answer" must be a first-class outcome.
- **Hallucination control** — citation verification against source spans, claim-level
  entailment checking, and what happens when it fails.
- **Prompt/model versioning** — prompts are code: versioned, reviewed, tested, and recorded
  on every derived fact (§9).
- **Evaluation** — this is `51-evaluation.md` and it is a required deliverable, not a nicety.
  Specify: eval set construction in Greek, size, who labels it, per-stage metrics
  (OCR CER/WER, NER F1, geocode accuracy@100m, ER pairwise F1, retrieval nDCG@10,
  citation precision, summary faithfulness), regression gates in CI, and drift monitoring.
- **Memory** — what persists across runs, where, and how it is invalidated. Be concrete;
  "memory agent" is not a design.

**Stack evaluation table** — for each of PostgreSQL, PostGIS, TimescaleDB, ClickHouse, DuckDB,
Neo4j, Memgraph, Apache AGE, OpenSearch/Elasticsearch, Qdrant, pgvector, Redis, S3-compatible
object storage, Kafka/Redpanda, NATS, Postgres-based queues, Temporal, Airflow/Dagster/Prefect,
Kubernetes, Nomad, plain VMs + Compose: **adopt / defer / reject**, with the requirement that
forces it and the operational cost at §3's team size. A defensible answer may reject most of
them; volume of adoption is not a virtue.

Likewise for event sourcing, CQRS, saga and outbox: each is a separate complexity tax. Adopt
only where a named requirement demands it.

---

## 12. Red team (stage S7)

Adopt an adversarial stance: *this design will fail; find out how.* Confirm or refute each
hypothesis below with reference to your own documents. "Not applicable" requires an argument.

1. Entity resolution is worse than assumed; problem counts and trends are systematically wrong.
2. Greek OCR quality on the historical corpus is below the threshold that makes backfill
   worthwhile — the €5,000 backfill buys noise.
3. LLM spend exceeds the ceiling within 60 days of production traffic.
4. The team cannot operate the proposed infrastructure; the system degrades unnoticed.
5. Sources break silently; freshness SLOs are violated without alerting.
6. The citizen channel is captured by a coordinated group and skews priorities.
7. A recommendation attributes blame to a named official on thin evidence; legal exposure.
8. A GDPR erasure request cannot actually be honoured because derived facts, embeddings and
   graph edges have no back-reference.
9. Retrieval quality in Greek is materially worse than the English benchmarks assumed.
10. Users do not trust the scores, ignore the ranking, and revert to reading the raw feed —
    the intelligence layer is dead weight.
11. Phase 1 does not ship in 10 weeks.
12. The system is technically correct and produces nothing the office would act on.

For each confirmed weakness: severity, likelihood, detection signal, mitigation, and residual
risk after mitigation. Then **apply the mitigations to the design** before writing the
executive summary.

---

## 13. Dashboard

Design for one specific 8am scenario: *the advisor has 15 minutes before a meeting and needs
to know what changed and what to raise.* Everything else is secondary.

Required surfaces: what changed since last visit · ranked problem list with visible reasoning ·
map with honest uncertainty · timeline per problem · evidence explorer down to the source span ·
graph explorer · contradiction and low-confidence flags · review queue · export with citations.

Anti-requirements: no vanity metrics, no chart that cannot be acted on, no score shown without
its explanation reachable in one click.

---

## 14. Adversarial and abuse model

Political products attract manipulation. Design for:
astroturfed citizen submissions · coordinated inauthentic reporting to inflate an issue ·
poisoning via a compromised or partisan source · prompt injection embedded in ingested
documents (**a PDF in the corpus is untrusted input to your LLM** — this is a live attack path,
treat it as such) · scraping and exfiltration of the aggregate ·
defamation via AI-generated attribution · insider misuse of the evidence base.

For each: detection, mitigation, and what the system does when it fires.

---

## 15. Acceptance criteria

The design is complete when an independent senior engineer can answer all of the following
from the documents alone:

1. What gets built in Phase 1, by whom, in what order, and what it costs to run.
2. Where a specific claim on the dashboard came from, end to end.
3. What happens when each external dependency fails.
4. Why each datastore exists and what was rejected in its place.
5. How extraction quality is measured, and what the current numbers are or will be.
6. How a GDPR erasure request is executed to completion.
7. What the first scaling bottleneck is and at what load it arrives.
8. Which parts are AI, why, and what happens when the AI is wrong.
9. What would make the team abandon this architecture.

Close with a self-assessment scoring the design 1–5 on each criterion, with the weakest two
named and a concrete plan to close them.
