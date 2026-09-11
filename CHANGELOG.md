# Changelog

## Unreleased

- Model catalog moved to the current Claude generation, verified against the published
  pricing page on 2026-09-11: `sonnet` → `claude-sonnet-5` ($2/$10 per MTok, down from
  Sonnet 4.6's $3/$15), `opus` → `claude-opus-5` ($5/$25, unchanged price), `haiku`
  stays `claude-haiku-4-5` ($1/$5). `cost_per_1k` for sonnet is now `0.002`.
- New `fable` tier (`claude-fable-5-1`, $10/$50) is priced and valid in custom routing
  tables; the default table and the low-confidence fallback still stop at Opus.
- Documented that the bundled benchmarks ran on Haiku 4.5 / Sonnet 4.6 / Opus 4.6 and
  have not been re-run on the models the tiers now return.
- Added `claude-router --eval [cases.json]` and `claude_router.evaluate`: routes a
  labelled prompt set (24 shipped, 2 per category) and reports category and tier
  accuracy, misroutes, and routed list-price cost against an all-Sonnet baseline.
- The standalone `router.py` now wraps unexpected Ollama request failures like the
  packaged router (the `requests.RequestException` handler had only landed in one copy).

- Pricing sources must be HTTPS documentation URLs on the first-party host; placeholders
  and unrelated hosts are rejected by both router entrypoints.
- Development installs include Pillow for the preview renderer; its specification names
  the required Menlo font. Pricing examples list the returned basis field.

Pricing contract. `route()` previously returned a single unlabelled `cost_per_1k` scalar
carried over from the 2026-03 benchmark runs; two of the three values no longer matched
the list price of the model ID actually returned.

- `route()` now returns `pricing` with the routed model's exact base input and output list
  prices (per MTok and per 1K), plus the `as_of` date and `source` URL they were read from
- Prices moved into one maintained catalog, `src/claude_router/model_pricing.json`, read by
  both the packaged router and the standalone `router.py`; validated on load, with model-ID
  and unit mismatches rejected rather than silently mis-pricing calls
- `cost_per_1k` is retained and unchanged in shape but is now derived from the catalog and
  documented as **deprecated, input tokens only** (`cost_per_1k_basis`). Corrected values:
  haiku `0.0008` → `0.001`, opus `0.015` → `0.005`; sonnet unchanged at `0.003`
- Removed the README monthly-cost projection and the example's character-count cost
  estimate; the example now prices a call from the token counts the API reports
- Benchmark results are unchanged; the PF-001 cost table and PF-002's "73% cheaper"
  multiplier are labelled as their historical 2026-03-20 run-date pricing
- Corrected `assets/preview-source.txt` and regenerated `assets/preview.png`; the old
  preview showed a `research`/`claude-sonnet-4-6` route for a command that actually
  routes to `eval`/`claude-haiku-4-5`. Added a deterministic renderer so the image can
  be reproduced from the checked-in CLI output.

## v1.0.0 — 2026-04-17

Initial public release. 5 scaffolds, embedding-based routing.

- Embedding-based task classification via nomic-embed-text (~10ms)
- 5 validated scaffolds: calibrated-scoring, insight-first, plan-first, substance-check, bug-hunt
- Routing table covering 10 task categories
- CLI and Python API
- Anti-findings documented: scaffolds break operational, coding, and safety-critical tasks
- Validated on 300+ blind-judged API calls
