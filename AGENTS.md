# AGENTS.md

`claude-router` is a local classifier that maps a prompt to a Claude tier and an optional scaffold.

## Use it for

- routing Claude prompts before the API call
- deciding when Haiku plus a scaffold is enough
- exposing a deterministic `model` and `scaffold_key` in automation

## Do not use it for

- non-Claude providers
- proving these exact routes transfer to every workload
- replacing evals on prompts that are outside the benchmarked categories

## Minimal commands

```bash
pip install -e ".[dev]"
claude-router "Evaluate this research paper for methodological rigor"
pytest -q
```

## Output shape

- `route()` returns `category`, `model`, `tier`, `scaffold_key`, `scaffold_text`, `confidence`, `low_confidence`, `cost_per_1k`
- low-confidence inputs fall back to Opus with no scaffold

## Success means

- routing returns a valid Claude model ID and scaffold choice
- empty input fails fast
- the README quick-start example matches the actual package API

## Common failure cases

- Ollama is not running or `nomic-embed-text` is unavailable
- custom routing data references a scaffold key that does not exist
- teams assume the provided centroids match an unrelated prompt distribution
