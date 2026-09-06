#!/usr/bin/env python3
"""
Basic usage example: classify a task → route → call Anthropic API with scaffold.

Requires:
  - Anthropic API key (ANTHROPIC_API_KEY env var)
  - Ollama running with nomic-embed-text
  - anthropic package installed

Usage:
  python examples/basic_usage.py
"""

import os
import sys

# Import the router
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from router import ClaudeRouter


def main():
    # 1. Initialize the router (loads centroids, routing table, scaffolds)
    print("Initializing router...")
    try:
        router = ClaudeRouter()
    except Exception as e:
        print(f"Router init failed: {e}")
        print("   Make sure Ollama is running: ollama serve")
        return

    # 2. Define a task to evaluate
    task = "Evaluate this research paper for methodological rigor and novelty"
    print(f"\nTask: {task}\n")

    # 3. Route the task (embedding → centroid match → lookup table)
    print("Routing...")
    try:
        route = router.route(task)
    except Exception as e:
        print(f"Routing failed: {e}")
        return

    # 4. Show the routing decision
    print(f"   Category:     {route['category']}")
    print(f"   Model:        {route['model']}")
    print(f"   Scaffold:     {route['scaffold_key'] or '(none)'}")
    print(f"   Confidence:   {route['confidence']:.4f}")
    print(f"   Input $/MTok: {route['pricing']['input_usd_per_mtok']}")
    print(f"   Output $/MTok: {route['pricing']['output_usd_per_mtok']}")

    if route["low_confidence"]:
        print("   Low confidence -- consider manual review")

    # 5. Build the scaffolded prompt
    print("\nBuilding prompt with scaffold...\n")
    prompt = router.build_prompt(task, route)
    if route["scaffold_text"]:
        print("--- SCAFFOLDED PROMPT ---")
        print(prompt)
        print("--- END PROMPT ---\n")

    # 6. Call Anthropic API with the scaffold
    print("Calling Anthropic API...")
    try:
        from anthropic import Anthropic
    except ImportError:
        print("anthropic package not installed")
        print("   Install: pip install anthropic")
        return

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set")
        return

    client = Anthropic(api_key=api_key)

    # Dummy research paper for demo
    research_text = """
    Title: Attention Is All You Need

    This paper introduces the Transformer architecture, using self-attention mechanisms
    to process sequences in parallel rather than sequentially. Training time improved
    40% and BLEU scores on translation improved to 28.4 on the WMT 2014 dataset.
    """

    try:
        response = client.messages.create(
            model=route["model"],
            max_tokens=500,
            system=route["scaffold_text"] if route["scaffold_text"] else None,
            messages=[
                {
                    "role": "user",
                    "content": f"{task}\n\n{research_text}",
                }
            ],
        )
        print("Response received\n")
        print(response.content[0].text)
    except Exception as e:
        print(f"API call failed: {e}")
        return

    # 7. Price this call from the token counts the API actually reported.
    #    Do not estimate tokens from character counts, and do not price a call from the
    #    input rate alone -- output costs 5x input on every tier.
    pricing = route["pricing"]
    usage = response.usage
    input_cost = usage.input_tokens * pricing["input_usd_per_mtok"] / 1_000_000
    output_cost = usage.output_tokens * pricing["output_usd_per_mtok"] / 1_000_000

    print(f"\nCost of this call ({route['model']}):")
    print(f"   Input:     {usage.input_tokens:>6} tok x ${pricing['input_usd_per_mtok']}/MTok  = ${input_cost:.6f}")
    print(f"   Output:    {usage.output_tokens:>6} tok x ${pricing['output_usd_per_mtok']}/MTok = ${output_cost:.6f}")
    print(f"   Total:     ${input_cost + output_cost:.6f}")
    print(f"   Prices as of {pricing['as_of']} -- {pricing['source']}")


if __name__ == "__main__":
    main()
