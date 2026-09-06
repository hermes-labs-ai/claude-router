# PF-002 Results Summary
**Experiment:** Expanded task coverage — 5 new categories
**Date:** 2026-03-20
**Conditions:** A (Haiku raw), B (Haiku scaffolded), C (Sonnet raw)
**Judge:** Claude Opus 4 (comparative scoring)

> The "73% cheaper" figures below are derived from the list prices in effect on the
> 2026-03-20 run date (see PF-001). **They are not current prices and not the prices of the
> model IDs the router ships with** — for those, see `src/claude_router/model_pricing.json`.
> Quality results are unchanged; only the cost multiplier is dated.

## Results by Category

### Content Drafting (5 tasks)
| Task | Winner | Notes |
|---|---|---|
| Tweet reply (tech influencer) | * C (Sonnet) | Most natural reply voice |
| LinkedIn hook (job rejection story) | * B (Scaffolded Haiku) | Punchy, makes you click |
| Cold DM (AI safety researcher) | * B | Direct, specific numbers, strong close |
| Substack title (null-result bias) | * B | Personal angle, "I tested 1500 scenarios" |
| Rewrite corporate sentence | * B | More human, first person |
**Category winner: B (Scaffolded Haiku) — 4/5 wins**
Key scaffold effect: "No em dashes, sound like a real person, NOT corporate" directly improved output.

### Status/Lookup (2 tasks)
All three adequate. All got math correct on lookup tasks.
Sonnet added extra analysis (ratio insight, dependency warning).
**Category: Tie (all sufficient) — Haiku raw is fine, no scaffolding needed**

### File Operations (2 tasks)
| Task | Winner | Notes |
|---|---|---|
| YAML bug detection | * C (Sonnet) | Most thorough (ssl_cert+key pairing context) |
| .gitignore generation | * C (Sonnet) | Most comprehensive |
**Category winner: C (Sonnet)**
Note: Scaffolding made B too terse on .gitignore — "include ONLY what's needed" constraint backfired.

### System Config (2 tasks)
| Task | Winner | Notes |
|---|---|---|
| Cron timeout fix | * C (Sonnet) | Idempotency + resume logic, specific commands |
| Telegram bot diagnostic | * C (Sonnet) | Webhook/polling conflict, specific API endpoints |
**Category winner: C (Sonnet)**

### Social Media Management (2 tasks)
| Task | Winner | Notes |
|---|---|---|
| Engagement pattern analysis | * C (Sonnet) | "Post something unfinished" insight |
| Posting schedule | * C (Sonnet) | "Front-load Mon-Wed" advice |
**Category winner: C (Sonnet) — but B was close**

---

## Combined Routing Table (PF-001 + PF-002)

### USE SCAFFOLDED HAIKU (73% cheaper, equal or better than Sonnet):
| Task Type | Evidence | Confidence |
|---|---|---|
| Evaluation / judging AI output | PF-001: MAE 1.0 vs Sonnet 1.2 | [Y] Tested |
| Content drafting (tweets, hooks, DMs, titles, rewrites) | PF-002: 4/5 wins vs Sonnet | [Y] Tested |
| Multi-step chains | PF-001: 9.0/10 raw, no scaffold needed | [Y] Tested |
| Status checks / lookups | PF-002: adequate raw | [Y] Tested |

### USE SONNET (Haiku can't match):
| Task Type | Evidence | Confidence |
|---|---|---|
| File operations (config analysis, file generation) | PF-002: Sonnet more thorough | [Y] Tested |
| System config / infrastructure | PF-002: Sonnet has specific commands | [Y] Tested |
| Social media analysis (pattern recognition) | PF-002: Sonnet adds better insight | [Y] Tested |
| Multi-context Q&A (close but Sonnet wins) | PF-001: 9.2 vs 9.6 | [Y] Tested |

### NOT YET TESTED:
| Task Type | Priority |
|---|---|
| Code review / bug finding | High |
| Complex research synthesis | Medium |
| Memory management | Low |
| Planning / prioritization | Low |

---

## Key Insights

1. **Scaffolded Haiku beats Sonnet on voice/tone tasks.** The constraint "sound like a real person, NOT corporate" is something Haiku follows more naturally than Sonnet. Sonnet's default voice is more polished but also more corporate.

2. **Sonnet wins on depth/detail tasks.** Config diagnostics, thorough file generation, nuanced analysis — Sonnet provides more specific commands, catches more edge cases, and adds strategic insight.

3. **Over-constraining backfires.** The "include ONLY what's needed" constraint made scaffolded Haiku's .gitignore too minimal. Scaffolds must be tuned per task type, not applied broadly.

4. **The light stack is taking shape.** Evaluation + content drafting + multi-step + status = a significant chunk of daily agent usage that can run on Haiku at 73% lower cost.
