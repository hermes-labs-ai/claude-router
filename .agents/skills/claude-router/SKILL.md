---
name: claude-router
description: Use when a call site needs a deterministic, local decision on which Claude model tier (Haiku/Sonnet/Opus) and prompt scaffold fits a given prompt before spending API tokens — claude-router classifies locally with embeddings and returns a model ID, scaffold text, and current list pricing. Local CLI/library, no MCP.
license: MIT
compatibility: Requires Python 3.10+, the `requests` and `numpy` packages, and a local Ollama instance running the nomic-embed-text embedding model.
---

# claude-router

claude-router is a local prompt router that picks the right Claude model tier
and prepends the right scaffold using local embeddings, before you call the
API. It classifies a prompt locally, chooses the right Claude tier, and
prepends the right scaffold when scaffolding actually improves quality for
that task category.

## Use it for

- Deciding locally, before an API call, whether a prompt needs Haiku, Sonnet,
  or Opus and whether it benefits from a scaffold
- Getting the routed model's current list price alongside the routing
  decision so cost can be estimated per call
- Evaluating classifier accuracy on a labelled prompt set before trusting the
  routing table in production (`--eval`)

## Do not use it for

- A general agent framework — it only returns a model ID and scaffold text,
  it does not call the Claude API itself
- Assuming these exact routes transfer unchanged to your workload — the
  bundled evidence was validated on the prior model generation and on the
  tool's own benchmark corpus
- Coding, design/debugging review, or operational tasks — the router
  deliberately sends these raw to Sonnet/Opus because scaffolds measurably
  hurt them

## Quickstart

```bash
pip install claude-router
ollama pull nomic-embed-text
```

```python
from claude_router import ClaudeRouter

router = ClaudeRouter()
result = router.route("Evaluate this research paper for methodological rigor")
print(result["model"], result["scaffold_key"])
print(result["pricing"]["input_usd_per_mtok"], result["pricing"]["output_usd_per_mtok"])
```

CLI:

```bash
claude-router "Write a blog post about Q2 results"
```

Evaluate the routing table's classification accuracy:

```bash
claude-router --eval
```

## Output shape

- `route(prompt)`: dict with `model` (Claude model ID), `scaffold_key`, and
  `pricing` (input/output $/MTok, basis, as-of date, source URL)
- `build_prompt(prompt)`: the prompt with the selected scaffold prepended
- `--eval`: reports `category_accuracy`, `tier_accuracy`, `misroutes`, and a
  list-price cost comparison against routing everything to Sonnet

## Common gotchas

- Requires a local Ollama instance with `nomic-embed-text` for embeddings —
  routing does not work without it, though `--eval`'s scoring path is
  offline.
- Low classifier confidence defaults to Opus as the safe fallback, not the
  category's normal route.
- `result["cost_per_1k"]` is deprecated and input-only; use
  `result["pricing"]` for anything that needs both input and output cost.
- The routing table has not been re-validated on the current Sonnet 5 / Opus
  5 generation for output quality — only for classification accuracy.

## More

Full docs and CLI reference:
https://github.com/hermes-labs-ai/claude-router
