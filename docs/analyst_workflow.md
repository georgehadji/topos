# Analyst Workflow — Web & Social Discovery

**Purpose:** Supplement Topos's six automated source plugins with manual discovery
from the open web (Perplexity Sonar), X/Twitter (Grok X Search), and broad web
search (Grok Web Search). Feed discovered URLs into the pipeline via
`POST /artifacts/ingest`.

**Cadence:** Weekly, 30–60 minutes.

---

## Prerequisites

- Access to [xAI Playground](https://console.x.ai/) with an API key.
- (Optional) Access to [Perplexity Playground](https://docs.perplexity.ai/) or
  an OpenRouter key with `perplexity/sonar-pro` access. If neither is available,
  run Sonar queries through Grok's `web_search` tool instead.

---

## Workflow

### 1. Grok Web Search — broad web discovery

**Prompt (paste into xAI Playground with `web_search` tool enabled):**

> What infrastructure problems (road damage, water outages, power cuts, flooding,
> public transport failures) were reported in Θεσσαλονίκη or Thessaloniki
> municipality in the past 7 days? Cite each source with its URL.

Then follow up:

> What health, safety, or environmental problems (pollution, waste, green space
> damage) were reported in Θεσσαλονίκη this week? Cite sources.

Then:

> What administrative or social issues (delays, missing services, bureaucratic
> failures, housing, education) were reported in Θεσσαλονίκη this week? Cite sources.

**Review:** Scan the cited URLs. Prioritize sources from these domains:
`thessaloniki.gr`, `voria.gr`, `typosthes.gr`, `parallaximag.gr`, `thessnews.gr`,
`makthes.gr`. Discard national news or clearly irrelevant results.

### 2. Grok X Search — social media monitoring

**Prompt (paste into xAI Playground with `x_search` tool enabled):**

> Search X for posts about "διακοπή νερού" OR "διακοπή ρεύματος" OR
> "καταστροφή δρόμου" OR "πλημμύρα" in Thessaloniki since YYYY-MM-DD.
> Show the post URL, author, and a summary of each. Exclude retweets.

Replace `YYYY-MM-DD` with 7 days ago.

Then:

> Search X for posts from @deddiede about scheduled power outages in
> Thessaloniki since YYYY-MM-DD.

**Review:** X posts by verified/official accounts (`@CityOfThess`, `@deddiede`,
`@pyrosvestiki`) are highest priority. Citizen posts are valuable but need
corroboration before ingesting.

### 3. Perplexity Sonar — targeted domain discovery (optional)

**Prompt (via Sonar API or OpenRouter → `perplexity/sonar-pro`):**

> What infrastructure problems were reported in thessaloniki.gr, voria.gr,
> typosthes.gr, or parallaximag.gr this week? Cite each source with its URL.

**Review:** Same as step 1, but Sonar's citations are always grounded in
search results — no unsourced claims possible.

---

## Ingesting Discovered URLs

For each high-signal URL:

1. Verify the URL is accessible and the content is about a citizen-affecting
   problem in Α΄ Θεσσαλονίκης.
2. Pull the source that covers it. `backfill` resolves the plugin from the
   source registry and enqueues what it fetches at the head of the pipeline:
   ```bash
   uv run topos-cli backfill --source sonar_web --limit 20 --json
   ```
   Use `--dry-run` first to see how much it would ingest without writing.
   `uv run topos-cli sources` lists every registered source and its config
   fields; override any of them with `--set key=value`.

   The HTTP equivalent is Διαύγεια-only and takes `org` / `limit`, not a URL:
   ```bash
   curl -X POST "http://localhost:8000/artifacts/ingest?org=&limit=3"
   ```
3. Verify the pipeline picked it up:
   ```bash
   uv run topos-cli pipeline --json
   ```

---

## Tracking

Log each session's results in `docs/PROGRESS.md` under a weekly heading:

```markdown
### Week 2025-07-27
- **Grok Web:** 12 cited URLs, 3 high-signal (road damage Εγνατία, water outage Καλαμαριά, garbage pileup Τούμπα)
- **X Search:** 18 posts, 2 from @deddiede (scheduled outages), 1 citizen post (flooded underpass)
- **Sonar:** 8 citations, 1 new discovery (municipal council meeting about waste collection)
- **Ingested:** 4 URLs → all reached DONE
- **Quality:** 1 false positive (national politics article), discard rate 1/4
```

After 4 weeks, review the tracking data to decide whether to automate any
discovery channel (see `implementation_plan.md` Phases 2, 2S).
