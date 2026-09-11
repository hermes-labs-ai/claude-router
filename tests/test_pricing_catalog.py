"""The pricing catalog is data, so it is a place bad data can enter. Reject it loudly.

Also pins the property that makes the catalog worth having: the packaged router and the
standalone repo-root router read the same file, so a price is corrected in one place.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import router as standalone_router
from claude_router import router as packaged_router
from tests.test_pricing_contract import AS_OF, OFFICIAL, SOURCE


def catalog() -> dict:
    return json.loads(packaged_router.PRICING_FILE.read_text())


def write_catalog(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "model_pricing.json"
    path.write_text(json.dumps(data))
    return path


def load_bad(tmp_path: Path, mutate) -> str:
    """Apply `mutate` to a copy of the shipped catalog and return the rejection message."""
    data = catalog()
    mutate(data)
    with pytest.raises(ValueError) as exc:
        packaged_router._load_pricing(write_catalog(tmp_path, data))
    return str(exc.value)


# --- the catalog agrees with the primary source -----------------------------------


def test_catalog_matches_official_published_prices() -> None:
    data = catalog()
    assert data["as_of"] == AS_OF
    assert data["source"] == SOURCE
    assert data["unit"] == packaged_router.PRICING_UNIT
    for tier, official in OFFICIAL.items():
        entry = data["models"][tier]
        assert entry["model_id"] == official["model_id"]
        assert entry["input"] == official["input"]
        assert entry["output"] == official["output"]


def test_catalog_covers_exactly_the_routed_tiers() -> None:
    assert set(catalog()["models"]) == set(packaged_router.MODEL_IDS)


# --- one catalog, both routers ----------------------------------------------------


def test_both_routers_read_the_same_catalog_file() -> None:
    assert standalone_router.PRICING_FILE.resolve() == packaged_router.PRICING_FILE.resolve()
    assert standalone_router.MODEL_IDS == packaged_router.MODEL_IDS
    assert standalone_router.MODEL_PRICING == packaged_router.MODEL_PRICING
    assert standalone_router.COST_PER_1K == packaged_router.COST_PER_1K


def test_both_routers_return_the_same_route_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two router files hold parallel copies of this logic, and have drifted before:
    commit 39dbf17 added a requests.RequestException handler to the packaged copy only.
    Pin the shape and the prices so the next drift fails here instead of in someone's bill.
    """
    results = []
    for module in (packaged_router, standalone_router):
        instance = module.ClaudeRouter()
        centroid = instance.centroids["eval"]
        monkeypatch.setattr(instance, "_embed", lambda _, c=centroid: c)
        results.append(instance.route("Score this summary"))

    packaged_result, standalone_result = results
    assert packaged_result.keys() == standalone_result.keys()
    for key in ("model", "tier", "pricing", "cost_per_1k", "cost_per_1k_basis"):
        assert packaged_result[key] == standalone_result[key]


def test_deprecated_scalar_is_derived_not_hand_written() -> None:
    for tier, pricing in packaged_router.MODEL_PRICING.items():
        assert packaged_router.COST_PER_1K[tier] == pricing["input_usd_per_1k"]
        assert pricing["input_usd_per_1k"] == round(pricing["input_usd_per_mtok"] / 1000.0, 6)
        assert pricing["output_usd_per_1k"] == round(pricing["output_usd_per_mtok"] / 1000.0, 6)


# --- adversarial catalogs ---------------------------------------------------------


def test_missing_catalog_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model pricing file not found"):
        packaged_router._load_pricing(tmp_path / "absent.json")


def test_unparseable_catalog_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "model_pricing.json"
    path.write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        packaged_router._load_pricing(path)


def test_non_object_catalog_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        packaged_router._load_pricing(write_catalog(tmp_path, [1, 2, 3]))


def test_wrong_unit_is_rejected(tmp_path: Path) -> None:
    """A per-1K catalog read as per-MTok would understate every price 1000x."""
    assert "'unit' must be" in load_bad(tmp_path, lambda d: d.__setitem__("unit", "usd_per_1k_tokens"))


@pytest.mark.parametrize("field", ["as_of", "source"])
def test_missing_provenance_is_rejected(tmp_path: Path, field: str) -> None:
    assert f"'{field}' must be a non-empty string" in load_bad(tmp_path, lambda d: d.pop(field))


@pytest.mark.parametrize("field", ["as_of", "source"])
def test_blank_provenance_is_rejected(tmp_path: Path, field: str) -> None:
    assert f"'{field}' must be a non-empty string" in load_bad(
        tmp_path, lambda d: d.__setitem__(field, "   ")
    )


def test_non_object_models_is_rejected(tmp_path: Path) -> None:
    assert "'models' must be a JSON object" in load_bad(tmp_path, lambda d: d.__setitem__("models", []))


def test_unknown_tier_is_rejected(tmp_path: Path) -> None:
    message = load_bad(tmp_path, lambda d: d["models"].__setitem__("mythos", {"model_id": "x"}))
    assert "unknown tier(s) mythos" in message


def test_missing_tier_is_rejected(tmp_path: Path) -> None:
    assert "missing an entry for tier 'opus'" in load_bad(tmp_path, lambda d: d["models"].pop("opus"))


def test_model_id_mismatch_is_rejected(tmp_path: Path) -> None:
    """The catalog must price the model the router actually returns, not a neighbour."""
    message = load_bad(
        tmp_path, lambda d: d["models"]["opus"].__setitem__("model_id", "claude-opus-4-8")
    )
    assert "'claude-opus-4-8'" in message
    assert "'claude-opus-5'" in message


@pytest.mark.parametrize("bad", ["5.0", None, True, [5.0], {"usd": 5.0}])
def test_non_numeric_price_is_rejected(tmp_path: Path, bad: object) -> None:
    assert "must be a number" in load_bad(
        tmp_path, lambda d: d["models"]["opus"].__setitem__("input", bad)
    )


@pytest.mark.parametrize("bad", [0, -1.5, float("inf"), float("nan")])
def test_non_positive_or_non_finite_price_is_rejected(tmp_path: Path, bad: float) -> None:
    assert "must be a positive" in load_bad(
        tmp_path, lambda d: d["models"]["sonnet"].__setitem__("output", bad)
    )


@pytest.mark.parametrize("field", ["input", "output"])
def test_missing_price_field_is_rejected(tmp_path: Path, field: str) -> None:
    assert "must be a number" in load_bad(tmp_path, lambda d: d["models"]["haiku"].pop(field))


def test_non_object_tier_entry_is_rejected(tmp_path: Path) -> None:
    assert "tier 'haiku' must be a JSON object" in load_bad(
        tmp_path, lambda d: d["models"].__setitem__("haiku", 1.0)
    )


def test_non_date_as_of_is_rejected(tmp_path: Path) -> None:
    """A placeholder as_of reads as provenance while carrying none."""
    assert "must be an ISO date" in load_bad(tmp_path, lambda d: d.__setitem__("as_of", "TBD"))


def test_price_that_underflows_to_zero_is_rejected(tmp_path: Path) -> None:
    """A converted positive rate must not silently become a free call."""
    message = load_bad(tmp_path, lambda d: d["models"]["haiku"].__setitem__("input", 5e-324))
    assert "underflows to $0.00 per 1K tokens" in message


def test_valid_catalog_with_different_prices_is_accepted(tmp_path: Path) -> None:
    """Validation checks shape and provenance, not that prices never change."""
    data = catalog()
    data["models"]["haiku"]["input"] = 2.0
    data["models"]["haiku"]["output"] = 9.0
    priced = packaged_router._load_pricing(write_catalog(tmp_path, data))
    assert priced["haiku"]["input_usd_per_1k"] == 0.002
    assert priced["haiku"]["output_usd_per_1k"] == 0.009


@pytest.mark.parametrize("module", [packaged_router, standalone_router])
@pytest.mark.parametrize("basis", [None, "", "cached", "batch", "regional"])
def test_non_base_pricing_basis_is_rejected(tmp_path: Path, module, basis) -> None:
    data = catalog()
    data["basis"] = basis
    with pytest.raises(ValueError, match="'basis' must be"):
        module._load_pricing(write_catalog(tmp_path, data))


@pytest.mark.parametrize("module", [packaged_router, standalone_router])
def test_pricing_basis_is_returned(module) -> None:
    for pricing in module.MODEL_PRICING.values():
        assert pricing["basis"] == "first_party_uncached_non_batch_global"


@pytest.mark.parametrize("module", [packaged_router, standalone_router])
def test_per_1k_conversion_preserves_catalog_precision(tmp_path: Path, module) -> None:
    data = catalog()
    data["models"]["haiku"]["input"] = 1.234567
    data["models"]["haiku"]["output"] = 0.0001
    pricing = module._load_pricing(write_catalog(tmp_path, data))["haiku"]
    assert pricing["input_usd_per_1k"] == 1.234567 / 1000
    assert pricing["output_usd_per_1k"] == 0.0001 / 1000


@pytest.mark.parametrize("module", [packaged_router, standalone_router])
@pytest.mark.parametrize("source", [
    "TBD",
    "http://platform.claude.com/docs/en/about-claude/pricing",
    "https://example.com/docs/pricing",
    "https://platform.claude.com.example.com/docs/pricing",
    "https://user@platform.claude.com/docs/pricing",
    "https://platform.claude.com/",
])
def test_non_first_party_documentation_source_is_rejected(tmp_path: Path, module, source) -> None:
    data = catalog()
    data["source"] = source
    with pytest.raises(ValueError, match="'source' must be an absolute HTTPS"):
        module._load_pricing(write_catalog(tmp_path, data))
