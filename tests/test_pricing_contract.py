"""Pricing contract: what `route()` says a model costs must be exact, labelled, and sourced.

`OFFICIAL` below is a deliberate, documented duplicate of the shipped catalog. It is
the independent authority this suite falsifies against: if the catalog silently drifts
from the published list price, only a second copy transcribed from the primary source
can detect it. Keep the two in sync by hand, and bump `AS_OF` when you re-check.
"""
from __future__ import annotations

import numpy as np
import pytest

from claude_router import ClaudeRouter

SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
AS_OF = "2026-09-06"

# Base (uncached, non-batch) first-party Claude API list prices, USD per million tokens,
# transcribed from SOURCE on AS_OF.
OFFICIAL = {
    "haiku": {"model_id": "claude-haiku-4-5", "input": 1.0, "output": 5.0},
    "sonnet": {"model_id": "claude-sonnet-4-6", "input": 3.0, "output": 15.0},
    "opus": {"model_id": "claude-opus-4-6", "input": 5.0, "output": 25.0},
}

# A routing category that deterministically resolves to each tier.
TIER_CATEGORY = {"haiku": "eval", "sonnet": "research", "opus": "conversation"}


@pytest.fixture
def router() -> ClaudeRouter:
    return ClaudeRouter()


def route_tier(router: ClaudeRouter, tier: str, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Route a prompt that lands on `tier`, with embedding stubbed out."""
    centroid = router.centroids[TIER_CATEGORY[tier]]
    monkeypatch.setattr(router, "_embed", lambda _: centroid)
    result = router.route("any prompt")
    assert result["tier"] == tier, f"fixture drift: expected {tier}, got {result['tier']}"
    return result


@pytest.mark.parametrize("tier", sorted(OFFICIAL))
def test_model_ids_are_not_relabelled(router: ClaudeRouter, tier: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The bundled IDs are tied to historical benchmark evidence — they must not move."""
    assert route_tier(router, tier, monkeypatch)["model"] == OFFICIAL[tier]["model_id"]


@pytest.mark.parametrize("tier", sorted(OFFICIAL))
def test_cost_per_1k_equals_official_base_input_price(
    router: ClaudeRouter, tier: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cost_per_1k` is input-only USD per 1K tokens, exact against the published price."""
    result = route_tier(router, tier, monkeypatch)
    expected = round(OFFICIAL[tier]["input"] / 1000.0, 6)
    assert result["cost_per_1k"] == expected


@pytest.mark.parametrize("tier", sorted(OFFICIAL))
def test_route_exposes_separate_input_and_output_pricing(
    router: ClaudeRouter, tier: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single scalar cannot price a call; input and output must both be returned."""
    pricing = route_tier(router, tier, monkeypatch)["pricing"]
    assert pricing["input_usd_per_mtok"] == OFFICIAL[tier]["input"]
    assert pricing["output_usd_per_mtok"] == OFFICIAL[tier]["output"]
    assert pricing["input_usd_per_1k"] == round(OFFICIAL[tier]["input"] / 1000.0, 6)
    assert pricing["output_usd_per_1k"] == round(OFFICIAL[tier]["output"] / 1000.0, 6)


def test_route_exposes_pricing_provenance(router: ClaudeRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prices are only checkable if the result says when they were read and from where."""
    result = route_tier(router, "sonnet", monkeypatch)
    assert result["pricing"]["as_of"] == AS_OF
    assert result["pricing"]["source"] == SOURCE
    assert result["cost_per_1k_basis"] == "input_tokens_only"


def test_low_confidence_fallback_is_priced_as_opus(router: ClaudeRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    zeros = np.zeros_like(next(iter(router.centroids.values())))
    monkeypatch.setattr(router, "_embed", lambda _: zeros)

    result = router.route("Ambiguous prompt")

    assert result["low_confidence"] is True
    assert result["pricing"]["model_id"] == OFFICIAL["opus"]["model_id"]
    assert result["pricing"]["output_usd_per_mtok"] == OFFICIAL["opus"]["output"]
