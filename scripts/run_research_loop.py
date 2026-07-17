#!/usr/bin/env python3
"""Run N iterations of the continuous research/evaluation loop and log results.

    python scripts/run_research_loop.py --iterations 1

Each iteration re-indexes the knowledge base, runs the evaluation gold set,
prints metrics + recommendations, and appends a JSON line to
research/logs/iterations.jsonl.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import argparse  # noqa: E402

from shia_aalim.evaluation.metrics import GoldQuery  # noqa: E402
from shia_aalim.research_loop import LoopConfig, run_loop  # noqa: E402
from shia_aalim.sources import load_registry_ids  # noqa: E402


def default_gold() -> list[GoldQuery]:
    """A tiny starter gold set over the Qur'an seed. Expand this over time."""
    return [
        GoldQuery("purification of the Ahl al-Bayt", {"quran-33-33"}),
        GoldQuery("love for the near relatives of the Prophet", {"quran-42-23"}),
        GoldQuery("who is your guardian wali", {"quran-5-55"}),
        GoldQuery("this day I have perfected your religion", {"quran-5-3"}),
        GoldQuery("there is no god but Allah the everliving", {"quran-2-255"}),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    config = LoopConfig(
        knowledge_dir=ROOT / "data" / "knowledge",
        registry_source_ids=load_registry_ids(ROOT / "data" / "sources" / "registry.yaml"),
        gold=default_gold(),
        log_path=ROOT / "research" / "logs" / "iterations.jsonl",
    )
    reports = run_loop(config, iterations=args.iterations)
    for report in reports:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
