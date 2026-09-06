#!/usr/bin/env python3
"""
claude-router: Route Claude API calls to the cheapest model that works.

Zero-LLM task classifier using embedding centroids. ~10ms per classification.
Injects task-specific scaffolds that make Haiku outperform Sonnet/Opus on
eval, research, and content tasks. Whether that saves money on your workload
depends on its input/output token mix; `route()` returns both list prices so
you can compute it rather than assume it.

Usage:
    from router import ClaudeRouter
    router = ClaudeRouter()
    result = router.route("Evaluate this research paper for quality")
    # -> {model: "claude-haiku-4-5", scaffold_key: "calibrated-scoring", ...}

Requires: requests, numpy, Ollama running with nomic-embed-text
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

import numpy as np
import requests

DATA_DIR = Path(__file__).parent / "data"
SCAFFOLDS_FILE = Path(__file__).parent / "scaffolds.json"
# The one maintained pricing catalog, shared with the packaged router. Edit prices there.
PRICING_FILE = Path(__file__).parent / "src" / "claude_router" / "model_pricing.json"
OLLAMA_URL = os.getenv("OLLAMA_EMBED_URL", "http://localhost:11434/api/embed")

# Public routing contract. The bundled benchmarks include historical model generations,
# so changing an ID needs fresh validation rather than treating old results as transferable.
MODEL_IDS: dict[str, str] = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

VALID_TIERS = frozenset(MODEL_IDS.keys())

PRICING_UNIT = "usd_per_million_tokens"
PRICING_BASIS = "first_party_uncached_non_batch_global"


def _load_pricing(path: Path = PRICING_FILE) -> dict[str, dict[str, Any]]:
    """Load and validate the shared model pricing catalog.

    One catalog backs both this module and the packaged router, so a price is
    corrected in exactly one place. Every field is checked up front: a malformed or
    mismatched catalog must fail loudly rather than silently mis-price calls.
    """
    try:
        with open(path) as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise ValueError(f"model pricing file not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"model pricing file is not valid JSON: {path} ({e})")
    if not isinstance(raw, dict):
        raise ValueError(f"model pricing file must be a JSON object: {path}")

    unit = raw.get("unit")
    if unit != PRICING_UNIT:
        raise ValueError(f"model pricing 'unit' must be '{PRICING_UNIT}', got {unit!r}: {path}")
    if raw.get("basis") != PRICING_BASIS:
        raise ValueError(
            f"model pricing 'basis' must be '{PRICING_BASIS}', "
            f"got {raw.get('basis')!r}: {path}"
        )
    for field in ("as_of", "source"):
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"model pricing '{field}' must be a non-empty string: {path}")
    # A visible as-of date is the whole point of the catalog, so it has to be a real date:
    # a placeholder like "TBD" would read as provenance while carrying none.
    try:
        date.fromisoformat(raw["as_of"])
    except ValueError:
        raise ValueError(
            f"model pricing 'as_of' must be an ISO date (YYYY-MM-DD), "
            f"got {raw['as_of']!r}: {path}"
        )

    models = raw.get("models")
    if not isinstance(models, dict):
        raise ValueError(f"model pricing 'models' must be a JSON object: {path}")
    unknown = sorted(set(models) - VALID_TIERS)
    if unknown:
        raise ValueError(
            f"model pricing has unknown tier(s) {', '.join(unknown)} "
            f"(valid: {', '.join(sorted(VALID_TIERS))}): {path}"
        )

    priced: dict[str, dict[str, Any]] = {}
    for tier, model_id in MODEL_IDS.items():
        if tier not in models:
            raise ValueError(f"model pricing is missing an entry for tier '{tier}': {path}")
        entry = models[tier]
        if not isinstance(entry, dict):
            raise ValueError(f"model pricing tier '{tier}' must be a JSON object: {path}")
        if entry.get("model_id") != model_id:
            raise ValueError(
                f"model pricing tier '{tier}' prices {entry.get('model_id')!r} but the "
                f"router routes that tier to {model_id!r}: {path}"
            )
        rates: dict[str, float] = {}
        for field in ("input", "output"):
            value = entry.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"model pricing tier '{tier}' field '{field}' must be a number, "
                    f"got {value!r}: {path}"
                )
            if not math.isfinite(value) or value <= 0:
                raise ValueError(
                    f"model pricing tier '{tier}' field '{field}' must be a positive "
                    f"finite price, got {value!r}: {path}"
                )
            rates[field] = float(value)
        per_1k = {f: rates[f] / 1000.0 for f in ("input", "output")}
        for field, value in per_1k.items():
            # Reject floating-point underflow instead of silently pricing calls as free.
            if value == 0.0:
                raise ValueError(
                    f"model pricing tier '{tier}' field '{field}' is {rates[field]!r} per "
                    f"million tokens, which underflows to $0.00 per 1K tokens: {path}"
                )
        priced[tier] = {
            "model_id": model_id,
            "input_usd_per_mtok": rates["input"],
            "output_usd_per_mtok": rates["output"],
            "input_usd_per_1k": per_1k["input"],
            "output_usd_per_1k": per_1k["output"],
            "basis": raw["basis"],
            "as_of": raw["as_of"],
            "source": raw["source"],
        }
    return priced


MODEL_PRICING: dict[str, dict[str, Any]] = _load_pricing()

# DEPRECATED. Input tokens only, USD per 1K — a call also costs output tokens, which
# this scalar does not and never did include. Derived from MODEL_PRICING so it cannot
# drift from the catalog. Prefer MODEL_PRICING[tier] or route()["pricing"].
COST_PER_1K: dict[str, float] = {tier: p["input_usd_per_1k"] for tier, p in MODEL_PRICING.items()}


class ClaudeRouter:
    """
    Embedding-based task classifier for Claude model routing.

    Classifies incoming prompts against pre-computed centroids (one per task
    category) using cosine similarity on nomic-embed-text embeddings. Returns
    the optimal model + scaffold for the task.

    Validated across 300+ blind-judged API calls.
    """

    def __init__(
        self,
        centroids_path: Optional[str | Path] = None,
        routing_table_path: Optional[str | Path] = None,
        scaffolds_path: Optional[str | Path] = None,
    ) -> None:
        centroids_path = Path(centroids_path) if centroids_path else DATA_DIR / "centroids.json"
        routing_table_path = Path(routing_table_path) if routing_table_path else DATA_DIR / "routing_table.json"
        scaffolds_path = Path(scaffolds_path) if scaffolds_path else SCAFFOLDS_FILE

        self.centroids = self._load_centroids(centroids_path)
        self.routing_table = self._load_json(routing_table_path, "routing table")
        self.scaffolds = self._load_json(scaffolds_path, "scaffolds")

        self._validate_config()

    @staticmethod
    def _load_json(path: Path, label: str) -> dict:
        try:
            with open(path) as f:
                data = json.load(f)
        except FileNotFoundError:
            raise ValueError(f"{label} file not found: {path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"{label} file is not valid JSON: {path} ({e})")
        if not isinstance(data, dict):
            raise ValueError(f"{label} file must be a JSON object: {path}")
        return data

    @staticmethod
    def _load_centroids(path: Path) -> dict[str, np.ndarray]:
        raw = ClaudeRouter._load_json(path, "centroids")
        if not raw:
            raise ValueError(f"centroids file is empty: {path}")
        return {k: np.array(v, dtype=np.float64) for k, v in raw.items()}

    def _validate_config(self) -> None:
        """Check routing table scaffold keys exist in scaffolds."""
        for category, route in self.routing_table.items():
            scaffold_key = route.get("scaffold")
            if scaffold_key is not None and scaffold_key not in self.scaffolds:
                raise ValueError(
                    f"routing table category '{category}' references scaffold "
                    f"'{scaffold_key}' which does not exist in scaffolds.json"
                )
            tier = route.get("model")
            if tier not in VALID_TIERS:
                raise ValueError(
                    f"routing table category '{category}' has unknown model tier "
                    f"'{tier}' (valid: {', '.join(sorted(VALID_TIERS))})"
                )

    def _embed(self, text: str) -> np.ndarray:
        """Embed text using nomic-embed-text via Ollama. ~5ms locally."""
        try:
            resp = requests.post(OLLAMA_URL, json={
                "model": "nomic-embed-text",
                "input": text[:500],
            }, timeout=10)
            resp.raise_for_status()
        except requests.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {OLLAMA_URL}. "
                "Is Ollama running? Start it with: ollama serve"
            )
        except requests.Timeout:
            raise RuntimeError(f"Ollama embedding request timed out ({OLLAMA_URL})")
        except requests.HTTPError as e:
            raise RuntimeError(f"Ollama returned an error: {e}")

        try:
            data = resp.json()
            return np.array(data["embeddings"][0], dtype=np.float64)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Unexpected Ollama response format: {e}")

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity, returning 0.0 for zero vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def route(self, text: str, min_confidence: float = 0.01) -> dict[str, Any]:
        """
        Classify a prompt and return the optimal model + scaffold.

        When confidence is below min_confidence, falls back to Opus (safe default).

        Args:
            text: The prompt to classify.
            min_confidence: Confidence threshold. Below this, route to Opus.

        Returns:
            dict with keys: category, model, tier, scaffold_key, scaffold_text,
            confidence, low_confidence, pricing, cost_per_1k, cost_per_1k_basis

            `pricing` carries the model's exact base input and output list prices
            (per million tokens and per 1K tokens) plus the `as_of` date and `source`
            they were read from. `cost_per_1k` is retained for backward compatibility
            and is input tokens only — priced calls need `pricing` as well.
        """
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty")

        emb = self._embed(text)
        scores = {cat: self._cosine_sim(emb, centroid)
                  for cat, centroid in self.centroids.items()}

        best_cat = max(scores, key=scores.get)
        sorted_scores = sorted(scores.values(), reverse=True)
        confidence = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else 1.0

        low_confidence = confidence < min_confidence

        # Look up routing table
        route = self.routing_table.get(best_cat, {"model": "sonnet", "scaffold": None})
        tier = route["model"]
        scaffold_key = route.get("scaffold")

        # Low confidence -> fall back to Opus (safe default)
        if low_confidence:
            tier = "opus"
            scaffold_key = None

        # Look up scaffold text
        scaffold_text = None
        if scaffold_key and scaffold_key in self.scaffolds:
            scaffold_text = self.scaffolds[scaffold_key]["text"]

        pricing = MODEL_PRICING[tier]

        return {
            "category": best_cat,
            "model": MODEL_IDS[tier],
            "tier": tier,
            "scaffold_key": scaffold_key,
            "scaffold_text": scaffold_text,
            "confidence": round(confidence, 4),
            "low_confidence": low_confidence,
            "pricing": dict(pricing),
            "cost_per_1k": pricing["input_usd_per_1k"],
            "cost_per_1k_basis": "input_tokens_only",
        }

    def build_prompt(self, text: str, route_result: Optional[dict] = None) -> str:
        """
        Build the final prompt with scaffold prepended (if applicable).

        Usage:
            result = router.route("Evaluate this paper")
            prompt = router.build_prompt("Evaluate this paper", result)
            # prompt now has scaffold constraints prepended
        """
        if route_result is None:
            route_result = self.route(text)

        if route_result.get("scaffold_text"):
            return route_result["scaffold_text"] + "\n\n" + text
        return text


if __name__ == "__main__":
    router = ClaudeRouter()

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        result = router.route(query)
        print(json.dumps(result, indent=2))
    else:
        tests = [
            "Evaluate this research paper for methodological rigor",
            "Write a LinkedIn post about our latest finding",
            "Review this Python function for bugs",
            "Check if the server is running and healthy",
            "Analyze these search results about prompt injection",
            "What do you think about our product strategy",
            "Run the deployment script on staging",
            "Score this AI-generated summary on a scale of 1-10",
        ]
        print(f"{'Category':<20} {'Model':<20} {'Scaffold':<22} {'Conf':>6}")
        print("-" * 70)
        for t in tests:
            r = router.route(t)
            scaffold = r["scaffold_key"] or "(none)"
            print(f"{r['category']:<20} {r['model']:<20} {scaffold:<22} {r['confidence']:>+.4f}")
            print(f"  -> {t[:65]}")
