"""The offline eval scores route() decisions; it must work with embeddings stubbed out."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from claude_router import ClaudeRouter
from claude_router.evaluate import EVAL_PROMPTS_FILE, evaluate, load_cases
from claude_router.router import MODEL_PRICING


@pytest.fixture
def router() -> ClaudeRouter:
    return ClaudeRouter()


def embed_by_label(router: ClaudeRouter, cases: list[dict], overrides: dict[str, str] | None = None):
    """Stub embedding: return the centroid of each prompt's labelled (or overridden) category."""
    label = {c["prompt"]: c["category"] for c in cases}
    label.update(overrides or {})
    return lambda text: router.centroids[label[text]]


def test_shipped_cases_cover_every_routing_category(router: ClaudeRouter) -> None:
    cases = load_cases()
    assert {c["category"] for c in cases} == set(router.routing_table)
    assert len(cases) == len({c["prompt"] for c in cases}), "duplicate prompts"


def test_perfect_routing_scores_full_accuracy(router: ClaudeRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = load_cases()
    monkeypatch.setattr(router, "_embed", embed_by_label(router, cases))

    report = evaluate(router, cases)

    assert report["cases"] == len(cases)
    assert report["category_accuracy"] == 1.0
    assert report["tier_accuracy"] == 1.0
    assert report["misroutes"] == []
    assert sum(report["tier_counts"].values()) == len(cases)


def test_misroute_is_reported_and_lowers_accuracy(router: ClaudeRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = load_cases()
    victim = next(c["prompt"] for c in cases if c["category"] == "eval")
    monkeypatch.setattr(router, "_embed", embed_by_label(router, cases, {victim: "conversation"}))

    report = evaluate(router, cases)

    assert report["category_accuracy"] == round((len(cases) - 1) / len(cases), 4)
    assert report["tier_accuracy"] == round((len(cases) - 1) / len(cases), 4)
    assert len(report["misroutes"]) == 1
    miss = report["misroutes"][0]
    assert miss["prompt"] == victim
    assert (miss["expected_category"], miss["routed_category"]) == ("eval", "conversation")
    assert (miss["expected_tier"], miss["routed_tier"]) == ("haiku", "opus")


def test_cost_is_list_price_at_stated_token_mix(router: ClaudeRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = load_cases()
    monkeypatch.setattr(router, "_embed", embed_by_label(router, cases))

    report = evaluate(router, cases, tokens_in=2000, tokens_out=500)

    expected_routed = sum(
        (2000 * MODEL_PRICING[router.routing_table[c["category"]]["model"]]["input_usd_per_mtok"]
         + 500 * MODEL_PRICING[router.routing_table[c["category"]]["model"]]["output_usd_per_mtok"])
        / 1_000_000
        for c in cases
    )
    sonnet = MODEL_PRICING["sonnet"]
    expected_baseline = len(cases) * (2000 * sonnet["input_usd_per_mtok"] + 500 * sonnet["output_usd_per_mtok"]) / 1_000_000

    cost = report["cost"]
    assert cost["routed_usd"] == round(expected_routed, 6)
    assert cost["baseline_usd"] == round(expected_baseline, 6)
    assert cost["baseline_model"] == "claude-sonnet-5"
    assert cost["routed_over_baseline"] == round(expected_routed / expected_baseline, 4)
    assert cost["as_of"] == sonnet["as_of"]
    assert cost["source"] == sonnet["source"]


def test_low_confidence_fallback_counts_as_opus_in_cost(router: ClaudeRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = [{"prompt": "ambiguous", "category": "eval"}]
    zeros = np.zeros_like(next(iter(router.centroids.values())))
    monkeypatch.setattr(router, "_embed", lambda _: zeros)

    report = evaluate(router, cases, tokens_in=1000, tokens_out=0)

    assert report["tier_counts"] == {"opus": 1}
    assert report["misroutes"][0]["low_confidence"] is True
    assert report["cost"]["routed_usd"] == round(MODEL_PRICING["opus"]["input_usd_per_1k"], 6)


def test_unknown_category_label_is_rejected(router: ClaudeRouter) -> None:
    with pytest.raises(ValueError, match="not in the routing table: poetry"):
        evaluate(router, [{"prompt": "x", "category": "poetry"}])


def test_unknown_baseline_tier_is_rejected(router: ClaudeRouter) -> None:
    with pytest.raises(ValueError, match="unknown baseline tier"):
        evaluate(router, load_cases(), baseline_tier="mythos")


@pytest.mark.parametrize("payload", ["[]", "{}", '{"cases": [{"prompt": "x"}]}', "{not json"])
def test_malformed_case_files_are_rejected(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "cases.json"
    path.write_text(payload)
    with pytest.raises(ValueError):
        load_cases(path)


def test_missing_case_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        load_cases(tmp_path / "absent.json")


def test_shipped_file_is_the_default(tmp_path: Path) -> None:
    assert load_cases() == json.loads(EVAL_PROMPTS_FILE.read_text())["cases"]
