#!/usr/bin/env python3
"""
Render the Gate console from seeded data. No GCP, no OAuth, no server.

    make console

Writes demo/out/console.html. Open it in a browser. This is the same
render_console() the Cloud Run app calls — the only difference is where the
state comes from.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.appraisal import Question, QuestionKind, build_queue, learn  # noqa: E402
from src.bidmath import (  # noqa: E402
    CompEstimate, Confidence, Lot, allocate, price_lot, summarize,
)
from src.gate import CycleView, render_console  # noqa: E402

SEED = pathlib.Path(__file__).parent / "seed"
OUT = pathlib.Path(__file__).parent / "out"
BUDGET_CAP = 2205.00
AUTO_SEND = 40.00

ANSWERS = {
    (QuestionKind.LOT_GROUPING, "stoneware"): "shelf lots are always the whole shelf",
    (QuestionKind.SCOPE, "advertising"): "only the marked piece unless caption says otherwise",
    (QuestionKind.APPETITE, "unsorted"): "skip box lots without captions",
}


def load_lots():
    lots = []
    for r in json.loads((SEED / "lots.json").read_text()):
        c = r["comp"]
        lots.append(Lot(
            lot_id=r["lot_id"], caption=r["caption"], category=r["category"],
            fit_score=r["fit_score"], condition_penalty=r["condition_penalty"],
            comp=CompEstimate(low=c["low"], high=c["high"],
                              source_count=c["source_count"],
                              confidence=Confidence(c["confidence"]))))
    return lots


def load_questions():
    return [
        Question(kind=QuestionKind(r["kind"]), category=r["category"],
                 prompt=r["prompt"], lot_ids=tuple(r["lot_ids"]),
                 value_at_stake=r["value_at_stake"],
                 confidence_gap=r["confidence_gap"], wants_photo=r["wants_photo"])
        for r in json.loads((SEED / "questions.json").read_text())
    ]


def main(cycle: str = "2026-08-22", prior_rules: bool = True) -> int:
    lots = load_lots()
    decisions = allocate([price_lot(l) for l in lots], BUDGET_CAP, AUTO_SEND)

    rules = []
    if prior_rules:
        seed_qs = load_questions()
        first = build_queue(seed_qs)
        rules = learn([(q, ANSWERS.get(q.rule_key, "noted")) for q in first.asked],
                      cycle="2026-07-11")

    queue = build_queue(load_questions(), rules)

    view = CycleView(
        cycle_id=cycle, auction_date="Saturday 2026-08-22",
        photos_ingested=428, queue=queue, decisions=decisions,
        summary=summarize(decisions), budget_cap=BUDGET_CAP,
        auto_send_threshold=AUTO_SEND,
        captions={l.lot_id: l.caption for l in lots},
        illustrative=True, lots_total=61,
    )

    OUT.mkdir(exist_ok=True)
    path = OUT / "console.html"
    path.write_text(render_console(view), encoding="utf-8")
    print(f"wrote {path}")
    print(f"  {view.photos_ingested} photos -> {view.summary.total_lots} lots")
    print(f"  {len(queue.asked)} questions asked, "
          f"{len(queue.auto_answered)} answered from memory")
    print(f"  {view.summary.allocated} bids "
          f"({view.summary.auto_send} auto-send, "
          f"{view.summary.needs_approval} need approval), "
          f"${view.summary.committed_all_in:,.2f} of ${BUDGET_CAP:,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
