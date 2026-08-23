"""Exercise Ollama's structured editorial contract with synthetic text."""

from __future__ import annotations

import argparse
import json

from clipper.providers.ollama import OllamaEditorialProvider


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3:8b-q4_K_M")
    args = parser.parse_args()

    transcript = (
        "[0.00-12.00] Small teams often lose time by automating a process before they understand it.\n"
        "[12.00-28.00] First do the work manually, record each decision, and identify the repeated parts.\n"
        "[28.00-45.00] Then automate only the stable steps and keep human review for exceptions.\n"
        "[45.00-60.00] That approach creates a smaller system, fewer surprises, and a clear payoff."
    )
    provider = OllamaEditorialProvider(args.base_url, args.model)
    candidates = provider._generate(provider._chunk_prompt(transcript))
    print(
        json.dumps(
            {
                "provider": provider.identity,
                "candidate_count": len(candidates),
                "schema_versions": sorted(
                    {item["schema_version"] for item in candidates}
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
