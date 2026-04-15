# claude-router

Route Claude API calls to the cheapest model that works. 5 validated scaffolds, embedding-based task classification in ~10ms. Validated on 300+ blind-judged API calls.

## Results

| Task | Best Setup | Cost | Quality vs. Baseline |
|------|-----------|------|------------|
| Eval/scoring | Haiku + scaffold | $0.06 | MAE 1.0 (vs Sonnet raw: 1.2) |
| Research | Sonnet + scaffold | $0.28 | 8.49/10 (vs Opus raw: 7.45) |
| Content | Haiku + scaffold | $0.06 | 4/5 blind wins vs Sonnet |
| Code review | Sonnet (raw) | $0.28 | 8.7/10 (vs Opus: 8.1) |

## Anti-findings

These are the blocker issues. The router handles them automatically:

- **Scaffolds break operational tasks** (0/9 success). Haiku treats constraints as meta-instructions instead of executing tasks.
- **Scaffolds hurt coding** (4.9 vs 6.4 raw). Don't scaffold code review, design, or debugging.
- **Opus doesn't scaffold**. Safety-critical evals need Opus raw (MAE 0.0), not scaffolded.

The routing table avoids these entirely: no scaffolds on operational, coding, safety-critical, or conversation tasks.

## Install

Requires: Python 3.10+, `requests`, `numpy`, and [Ollama](https://ollama.com) running locally with nomic-embed-text.

```bash
pip install claude-router
ollama pull nomic-embed-text
```

## Quick start

```python
from claude_router import ClaudeRouter

router = ClaudeRouter()
result = router.route("Evaluate this research paper for methodological rigor")

print(result["model"])           # claude-haiku-4-5
print(result["scaffold_key"])    # calibrated-scoring
print(result["cost_per_1k"])     # 0.0008

# Build prompt with scaffold prepended
prompt = router.build_prompt("Evaluate this research paper...")
# → Pass prompt as system message to Anthropic API
```

Or CLI:

```bash
python router.py "Write a blog post about Q2 results"
```

## How it works

1. Embed your prompt using nomic-embed-text (~5ms)
2. Compare against pre-computed task-category centroids
3. Look up routing table: category → model + scaffold
4. Return model ID and scaffold text

No LLM calls for routing. All locally in ~10ms. Low confidence (router accuracy 74% on 26-prompt benchmark) defaults to Opus.

## The 5 scaffolds

Each scaffold is validated through blind evaluation. They work by constraining the model's output space to the task structure.

See [scaffolds.json](scaffolds.json) for full text and evidence:

- **calibrated-scoring**: Integer 1-10, cite evidence, not generous/critical
- **insight-first**: Lead non-obvious, concrete recs, 3-4 sentences
- **plan-first**: g:goal;c:constraints;s:steps;r:risks prefix
- **substance-check**: Real gaps not surface, name issue and location
- **bug-hunt**: Specific bugs, line numbers, severity, one-line fix

## Routing table

```
eval              → Haiku   + calibrated-scoring
research          → Sonnet  + insight-first
content           → Haiku   + insight-first
analytical_review → Haiku   + substance-check
search            → Haiku   + plan-first

coding            → Sonnet  (raw)
operational       → Sonnet  (raw)
status_check      → Haiku   (raw)
conversation      → Opus    (raw)
safety_critical   → Opus    (raw)
```

Low confidence → Opus (safe default).

## Cost math

For 10,000 Claude API calls/month:

| Strategy | Cost | Quality |
|----------|------|---------|
| All Opus | $6,800 | Baseline |
| All Sonnet | $2,800 | Lower on eval, equal on code |
| claude-router | ~$620 | Equal or better on eval/research/content |

## Customization

Swap scaffolds, centroids, or routing table:

```python
router = ClaudeRouter(
    centroids_path="my_centroids.json",
    routing_table_path="my_routing.json",
    scaffolds_path="my_scaffolds.json"
)
```

## Limitations

- Requires Ollama locally (for embeddings)
- Centroids trained on one task distribution — test on your workload
- Router misclassifies 26% of tasks — low confidence defaults to Opus
- Anti-findings are real: scaffolds on coding/operational make things worse
- Lite mode (Haiku-first routing for max savings) planned for v1.1

## Evidence

Benchmarks: [benchmarks/](benchmarks/) | Raw citations: [scaffolds.json](scaffolds.json) | License: [MIT](LICENSE)

Key experiments: 4-condition code/research crossover, scaffolds-vs-operational stress test, scaffolded Sonnet beats Opus 75% on research (6/8 blind wins, 140 API calls).

## Hermes Labs Ecosystem

claude-router is part of the [Hermes Labs](https://hermes-labs.ai) open-source suite:

- [**lintlang**](https://github.com/roli-lpci/lintlang) — Static linter for AI agent tool descriptions and system prompts
- [**little-canary**](https://github.com/roli-lpci/little-canary) — Prompt injection detection
- [**zer0dex**](https://github.com/roli-lpci/zer0dex) — Dual-layer memory for AI agents
- [**zer0lint**](https://github.com/roli-lpci/zer0lint) — mem0 extraction diagnostics
- [**suy-sideguy**](https://github.com/roli-lpci/suy-sideguy) — Autonomous agent watchdog
- [**quickthink**](https://github.com/roli-lpci/quickthink) — Planning scaffolding for local LLMs

---

Need this calibrated to your pipeline? [Open an issue](https://github.com/roli-lpci/claude-router/issues) or reach out to [Hermes Labs](https://hermes-labs.ai) for custom scaffolds and production integration.
