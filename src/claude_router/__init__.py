"""
claude-router: Embedding-based scaffold router for Claude API.

Routes tasks to the right model + scaffold using centroid matching.
Zero LLM calls for routing. ~10ms classification. By Hermes Labs.
"""

from __future__ import annotations

from claude_router.router import ClaudeRouter, _cli

__all__ = ["ClaudeRouter"]
__version__ = "1.0.0"
