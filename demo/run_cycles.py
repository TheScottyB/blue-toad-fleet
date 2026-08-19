#!/usr/bin/env python3
"""
The learning beat, runnable locally with no GCP and no external dependency.

Cycle 1: the agent asks. Answers become standing rules.
Cycle 2: the same gallery, re-run under those rules — it asks fewer.

Conventions generalise ("shelf lots mean the whole shelf"). Questions about a
specific object do not — asking again whether *this* base has a mark is
correct behaviour, not a memory failure. So the queue settles rather than
going to zero, which is the honest result.

    make cycles
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.appraisal import (  # noqa: E402
    Question, QuestionKind, build_queue, learn,
)

SEED = pathlib.Path(__file__).parent / "seed" / "questions.json"
CAP = 12

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, YELLOW, CYAN, MAGENTA = "\033[32m", "\033[33m", "\033[36m", "\033[35m"


def load() -> list[Question]:
    return [
        Question(kind=QuestionKind(r["kind"]), category=r["category"],
                 prompt=r["prompt"], lot_ids=tuple(r["lot_ids"]),
                 value_at_stake=r["value_at_stake"],
                 confidence_gap=r["confidence_gap"], wants_photo=r["wants_photo"])
        for r in json.loads(SEED.read_text())
    ]


ANSWERS = {
    (QuestionKind.LOT_GROUPING, "stoneware"): "shelf lots are always the whole shelf",
    (QuestionKind.LOT_GROUPING, "cameras"): "extra angles are the same lot as the prior caption",
    (QuestionKind.SCOPE, "advertising"): "only the marked piece unless caption says otherwise",
    (QuestionKind.SCOPE, "vintage toys"): "count pieces from the photo; assume one lot",
    (QuestionKind.SCOPE, "railroad"): "railroadiana groupings sell as one lot here",
    (QuestionKind.APPETITE, "native american"): "skip — no provenance, no market for us",
    (QuestionKind.APPETITE, "unsorted"): "skip box lots without captions",
}


def show(cycle_name: str, rules: list) -> tuple:
    r = build_queue(load(), rules, cap=CAP)
    print(f"\n{BOLD}{cycle_name}{RESET}")
    print(f"{DIM}{'─' * 74}{RESET}")

    if r.auto_answered:
        print(f"{GREEN}Answered from memory ({len(r.auto_answered)}) — not asked:{RESET}")
        for qq, rule in r.auto_answered:
            print(f"  {GREEN}✓{RESET} {DIM}[{qq.kind.value}/{qq.category}]{RESET} "
                  f"{rule.answer}  {DIM}(learned {rule.learned_cycle}, "
                  f"{len(qq.lot_ids)} lot(s)){RESET}")
        print()

    print(f"{YELLOW}Asked ({len(r.asked)}):{RESET}")
    for i, qq in enumerate(r.asked, 1):
        cam = f" {MAGENTA}[photo]{RESET}" if qq.wants_photo else ""
        print(f"  {i:>2}. {qq.prompt}{cam}")
        print(f"      {DIM}{qq.kind.value} · {qq.category} · {len(qq.lot_ids)} lot(s) "
              f"· impact {qq.impact}{RESET}")

    if r.dropped:
        print(f"\n{DIM}Over cap, not asked — {len(r.flagged_lot_ids)} lot(s) "
              f"ship flagged low-confidence rather than blocking the sheet.{RESET}")
    return r, len(r.asked)


def main() -> int:
    print(f"\n{BOLD}BLUE TOAD FLEET — intake clarification, two cycles{RESET}")
    print(f"{DIM}Same gallery both times. Cap {CAP} questions per cycle.{RESET}")

    c1, n1 = show("CYCLE 1  ·  2026-07-11  ·  no prior rules", [])

    answered = [(q, ANSWERS.get(q.rule_key, "noted")) for q in c1.asked]
    rules = learn(answered, cycle="2026-07-11")

    print(f"\n{CYAN}Learned {len(rules)} standing rule(s) from {len(answered)} "
          f"answer(s).{RESET}")
    print(f"{DIM}Only conventions generalise. Answers about one object teach "
          f"nothing reusable.{RESET}")

    c2, n2 = show("CYCLE 2  ·  same gallery, re-run under cycle-1 rules", rules)

    print(f"\n{BOLD}RESULT{RESET}")
    print(f"  cycle 1 asked   {BOLD}{n1}{RESET}")
    print(f"  cycle 2 asked   {BOLD}{n2}{RESET}   "
          f"{GREEN}({n1 - n2} fewer, {len(c2.auto_answered)} answered from memory){RESET}")
    print(f"\n{DIM}It settles rather than reaching zero, which is correct: "
          f"a maker's mark on a\nnew object is a new question every time. "
          f"That is the honest version of learning.{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
