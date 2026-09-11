"""Pricing contract: what `route()` says a model costs must be exact, labelled, and sourced.

`OFFICIAL` below is a deliberate, documented duplicate of the shipped catalog. It is
the independent authority this suite falsifies against: if the catalog silently drifts
from the published list price, only a second copy transcribed from the primary source
can detect it. Keep the two in sync by hand, and bump `AS_OF` when you re-check.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from claude_router import ClaudeRouter
from claude_router import router as packaged_router

SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
AS_OF = "2026-09-11"

# Base (uncached, non-batch) first-party Claude API list prices, USD per million tokens,
# transcribed from SOURCE on AS_OF.
OFFICIAL = {
    "haiku": {"model_id": "claude-haiku-4-5", "input": 1.0, "output": 5.0},
    "sonnet": {"model_id": "claude-sonnet-5", "input": 2.0, "output": 10.0},
    "opus": {"model_id": "claude-opus-5", "input": 5.0, "output": 25.0},
    "fable": {"model_id": "claude-fable-5-1", "input": 10.0, "output": 50.0},
}

# A routing category that deterministically resolves to each tier in the shipped table.
# `fable` has no default route (see MODEL_IDS), so it is exercised through a custom table.
TIER_CATEGORY = {"haiku": "eval", "sonnet": "research", "opus": "conversation"}
CUSTOM_TIER_CATEGORY = "safety_critical"


@pytest.fixture
def router() -> ClaudeRouter:
    return ClaudeRouter()


def router_for_tier(tier: str, tmp_path: Path) -> tuple[ClaudeRouter, str]:
    """A router plus a category that routes to `tier`, via a custom table when needed."""
    if tier in TIER_CATEGORY:
        return ClaudeRouter(), TIER_CATEGORY[tier]
    table = json.loads(Path(packaged_router.DATA_DIR, "routing_table.json").read_text())
    table[CUSTOM_TIER_CATEGORY] = {"model": tier, "scaffold": None}
    path = tmp_path / "routing_table.json"
    path.write_text(json.dumps(table))
    return ClaudeRouter(routing_table_path=path), CUSTOM_TIER_CATEGORY


def route_tier(router: ClaudeRouter, tier: str, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Route a prompt that lands on `tier`, with embedding stubbed out."""
    centroid = router.centroids[TIER_CATEGORY[tier]]
    monkeypatch.setattr(router, "_embed", lambda _: centroid)
    result = router.route("any prompt")
    assert result["tier"] == tier, f"fixture drift: expected {tier}, got {result['tier']}"
    return result


def route_any_tier(tier: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Like route_tier, but also covers tiers the shipped table never routes to."""
    router, category = router_for_tier(tier, tmp_path)
    centroid = router.centroids[category]
    monkeypatch.setattr(router, "_embed", lambda _: centroid)
    result = router.route("any prompt")
    assert result["tier"] == tier, f"fixture drift: expected {tier}, got {result['tier']}"
    return result


@pytest.mark.parametrize("tier", sorted(OFFICIAL))
def test_model_ids_are_not_relabelled(tier: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A pricing-only change must not silently alter the public routing contract."""
    assert route_any_tier(tier, tmp_path, monkeypatch)["model"] == OFFICIAL[tier]["model_id"]


@pytest.mark.parametrize("tier", sorted(OFFICIAL))
def test_cost_per_1k_equals_official_base_input_price(
    tier: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cost_per_1k` is input-only USD per 1K tokens, exact against the published price."""
    result = route_any_tier(tier, tmp_path, monkeypatch)
    expected = round(OFFICIAL[tier]["input"] / 1000.0, 6)
    assert result["cost_per_1k"] == expected


@pytest.mark.parametrize("tier", sorted(OFFICIAL))
def test_route_exposes_separate_input_and_output_pricing(
    tier: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single scalar cannot price a call; input and output must both be returned."""
    pricing = route_any_tier(tier, tmp_path, monkeypatch)["pricing"]
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


def test_default_routing_table_never_routes_to_fable(router: ClaudeRouter) -> None:
    """Fable 5.1 is priced and routable, but only a custom table may send traffic there."""
    assert "fable" in packaged_router.VALID_TIERS
    assert {route["model"] for route in router.routing_table.values()} == {"haiku", "sonnet", "opus"}


def test_custom_table_can_route_to_fable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = route_any_tier("fable", tmp_path, monkeypatch)
    assert result["model"] == "claude-fable-5-1"
    assert result["scaffold_key"] is None
    assert result["pricing"]["output_usd_per_mtok"] == 50.0
