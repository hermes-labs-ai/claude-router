"""Offline routing evaluation against a small labelled prompt set.

Scores the routing decisions the router makes on prompts with a known expected
category, and compares the routed tiers' list prices against an all-Sonnet baseline.
Routing itself still needs Ollama for embeddings; the scoring here is pure arithmetic
over `route()` results, so tests can drive it with a stubbed `_embed`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from claude_router.router import MODEL_IDS, MODEL_PRICING, ClaudeRouter

EVAL_PROMPTS_FILE = Path(__file__).parent / "eval_prompts.json"


def load_cases(path: Optional[str | Path] = None) -> list[dict[str, str]]:
    """Load labelled cases: a JSON list of {"prompt": str, "category": str}."""
    path = Path(path) if path else EVAL_PROMPTS_FILE
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ValueError(f"eval prompts file not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"eval prompts file is not valid JSON: {path} ({e})")
    cases = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"eval prompts file must hold a non-empty 'cases' list: {path}")
    for i, case in enumerate(cases):
        if not isinstance(case, dict) or not case.get("prompt") or not case.get("category"):
            raise ValueError(f"eval case {i} needs non-empty 'prompt' and 'category': {path}")
    return cases


def _call_cost(tier: str, tokens_in: int, tokens_out: int) -> float:
    pricing = MODEL_PRICING[tier]
    return (
        tokens_in * pricing["input_usd_per_mtok"] + tokens_out * pricing["output_usd_per_mtok"]
    ) / 1_000_000


def evaluate(
    router: ClaudeRouter,
    cases: list[dict[str, str]],
    tokens_in: int = 1000,
    tokens_out: int = 1000,
    baseline_tier: str = "sonnet",
) -> dict[str, Any]:
    """Route every case and score category accuracy, tier accuracy, and cost.

    Cost is estimated at `tokens_in` input and `tokens_out` output tokens per call, at
    the catalog list prices, for the tiers the router actually chose versus sending
    every prompt to `baseline_tier`. It is a list-price estimate with a stated token
    mix, not a measurement of any real workload.
    """
    if baseline_tier not in MODEL_IDS:
        raise ValueError(f"unknown baseline tier {baseline_tier!r} (valid: {', '.join(sorted(MODEL_IDS))})")
    if tokens_in < 0 or tokens_out < 0:
        raise ValueError("tokens_in and tokens_out must be non-negative")

    unknown = sorted({c["category"] for c in cases} - set(router.routing_table))
    if unknown:
        raise ValueError(f"eval cases reference categories not in the routing table: {', '.join(unknown)}")

    misroutes: list[dict[str, Any]] = []
    category_hits = tier_hits = 0
    routed_cost = baseline_cost = 0.0
    tier_counts: dict[str, int] = {}

    for case in cases:
        result = router.route(case["prompt"])
        expected_category = case["category"]
        expected_tier = router.routing_table[expected_category]["model"]
        tier = result["tier"]
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        routed_cost += _call_cost(tier, tokens_in, tokens_out)
        baseline_cost += _call_cost(baseline_tier, tokens_in, tokens_out)

        if result["category"] == expected_category:
            category_hits += 1
        if tier == expected_tier:
            tier_hits += 1
        if result["category"] != expected_category or tier != expected_tier:
            misroutes.append({
                "prompt": case["prompt"],
                "expected_category": expected_category,
                "routed_category": result["category"],
                "expected_tier": expected_tier,
                "routed_tier": tier,
                "confidence": result["confidence"],
                "low_confidence": result["low_confidence"],
            })

    n = len(cases)
    return {
        "cases": n,
        "category_accuracy": round(category_hits / n, 4),
        "tier_accuracy": round(tier_hits / n, 4),
        "tier_counts": dict(sorted(tier_counts.items())),
        "misroutes": misroutes,
        "cost": {
            "tokens_in_per_call": tokens_in,
            "tokens_out_per_call": tokens_out,
            "routed_usd": round(routed_cost, 6),
            "baseline_tier": baseline_tier,
            "baseline_model": MODEL_IDS[baseline_tier],
            "baseline_usd": round(baseline_cost, 6),
            "routed_over_baseline": round(routed_cost / baseline_cost, 4) if baseline_cost else None,
            "basis": MODEL_PRICING[baseline_tier]["basis"],
            "as_of": MODEL_PRICING[baseline_tier]["as_of"],
            "source": MODEL_PRICING[baseline_tier]["source"],
        },
    }
