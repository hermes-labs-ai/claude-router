#!/usr/bin/env python3
"""
claude-router: Route Claude API calls to the cheapest model that works.

Zero-LLM task classifier using embedding centroids. ~10ms per classification.
Injects task-specific scaffolds that make Haiku outperform Sonnet/Opus on
eval, research, and content tasks. 11x cost reduction, blind-eval validated.

Usage:
    from router import ClaudeRouter
    router = ClaudeRouter()
    result = router.route("Evaluate this research paper for quality")
    # -> {model: "claude-haiku-4-5", scaffold_key: "calibrated-scoring", ...}

Requires: requests, numpy, Ollama running with nomic-embed-text
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
import requests

DATA_DIR = Path(__file__).parent
SCAFFOLDS_FILE = Path(__file__).parent / "scaffolds.json"
OLLAMA_URL = os.getenv("OLLAMA_EMBED_URL", "http://localhost:11434/api/embed")

MODEL_IDS: dict[str, str] = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

COST_PER_1K: dict[str, float] = {
    "haiku": 0.0008,
    "sonnet": 0.003,
    "opus": 0.015,
}

VALID_TIERS = frozenset(MODEL_IDS.keys())


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
            confidence, low_confidence, cost_per_1k
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

        return {
            "category": best_cat,
            "model": MODEL_IDS[tier],
            "tier": tier,
            "scaffold_key": scaffold_key,
            "scaffold_text": scaffold_text,
            "confidence": round(confidence, 4),
            "low_confidence": low_confidence,
            "cost_per_1k": COST_PER_1K[tier],
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


def _cli():
    """CLI entry point for claude-router."""
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


if __name__ == "__main__":
    _cli()
