# Preview spec

- Dimensions: `1600x900`
- Format: static PNG terminal card
- Background: page `#0b1020`, panel `#111827`, header `#0f172a`
- Typography: monospace (`Menlo` or fallback)
- Padding: 72px outer, 48px inner
- Chrome: rounded panel with three header dots
- Prompt color: `#60a5fa`
- Body color: `#e5e7eb`
- Accent colors: green `#34d399`, yellow `#fbbf24`, red `#f87171`
- Command shown: `claude-router "Evaluate this research paper for methodological rigor"`
- Exact output shown: the contents of `assets/preview-source.txt` — a real run of the
  command above, with only `scaffold_text` elided for width
- Rule: use real CLI output only, no mock UI, no GIFs, no stock art
- Rule: regenerate `assets/preview.png` from `assets/preview-source.txt` whenever that file
  changes, so the image never outlives the output it claims to show

## Status

`assets/preview.png` is **stale and pending regeneration**. It predates the current
`preview-source.txt`: it shows a `research`/`claude-sonnet-4-6` route for a command that
actually routes to `eval`/`claude-haiku-4-5`, and a bare `cost_per_1k` with no input/output
label. Regenerate it against `preview-source.txt` before the next release.
