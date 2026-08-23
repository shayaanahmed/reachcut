"""Exercise Ollama's structured editorial contract with synthetic text."""

from __future__ import annotations

import argparse
import json

from clipper.domain.editing_plan import TimeRange
from clipper.providers.ollama import CandidateOption, OllamaEditorialProvider


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3:8b-q4_K_M")
    args = parser.parse_args()

    transcript = " ".join(
        [
            "Small teams often lose time by automating before they understand a process.",
            "First do the work manually, record decisions, and identify repeated parts.",
            "Then automate stable steps and keep human review for exceptions.",
            "That creates a smaller system, fewer surprises, and a clear payoff.",
        ]
    )
    option = CandidateOption(
        "c0000", TimeRange(start_seconds=0, end_seconds=60), transcript
    )
    provider = OllamaEditorialProvider(args.base_url, args.model)
    candidates = provider._generate(
        provider._batch_prompt([option]), allowed_ids={option.candidate_id}
    )
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
