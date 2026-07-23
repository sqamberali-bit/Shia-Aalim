#!/usr/bin/env python3
"""End-to-end demo: load seed knowledge, index it, answer a question, and draft
a lecture outline — using only the stdlib reference pipeline (no installs).

    python scripts/demo.py "What does the Qur'an say about the Ahl al-Bayt?"
    python scripts/demo.py --lecture "The purification of the Ahl al-Bayt"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from shia_aalim.generation.answer import AnswerGenerator  # noqa: E402
from shia_aalim.generation.lecture import LectureGenerator  # noqa: E402
from shia_aalim.generation.synthesizer import make_synthesizer  # noqa: E402
from shia_aalim.ingestion.loaders import iter_knowledge_dir  # noqa: E402
from shia_aalim.research_loop import build_index  # noqa: E402
from shia_aalim.sources import load_registry_ids  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="a research question, or a lecture topic with --lecture")
    parser.add_argument("--lecture", action="store_true", help="draft a lecture outline instead")
    parser.add_argument("--k", type=int, default=6)
    parser.add_argument(
        "--synthesize", default="none", metavar="SPEC",
        help="LLM synthesizer: none | mock | claude:<model> (needs [llm] extra + ANTHROPIC_API_KEY)",
    )
    args = parser.parse_args()

    docs = list(iter_knowledge_dir(ROOT / "data" / "knowledge"))
    print(f"Loaded {len(docs)} documents from the knowledge base.\n")
    retriever = build_index(docs)

    synthesizer = make_synthesizer(args.synthesize)

    if args.lecture:
        lecture = LectureGenerator(retriever, synthesizer=synthesizer).generate(args.query)
        print(lecture.to_markdown())
        return 0

    known = load_registry_ids(ROOT / "data" / "sources" / "registry.yaml")
    gen = AnswerGenerator(retriever, synthesizer=synthesizer, known_source_ids=known)
    answer = gen.answer(args.query, k=args.k)
    print(gen.format_markdown(answer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
