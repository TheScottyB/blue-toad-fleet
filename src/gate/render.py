"""
The Gate console.

A pure function from cycle state to HTML. No framework, no dependencies, no I/O
— which means it renders identically in the credential-free demo, in tests, and
behind the Cloud Run app. The console is not a review surface bolted on at the
end; it is where the sheet's quality is actually made, because the question
queue lives here.
"""

from dataclasses import dataclass, field
from html import escape

from src.appraisal import QueueResult
from src.bidmath import Decision, Priority, SheetSummary


@dataclass
class CycleView:
    cycle_id: str
    auction_date: str
    photos_ingested: int
    queue: QueueResult
    decisions: list[Decision]
    summary: SheetSummary
    budget_cap: float
    auto_send_threshold: float
    captions: dict[str, str] = field(default_factory=dict)
    deadline: str = "Friday 8:00 PM"


_CSS = """
:root{--bg:#0f1115;--card:#171a21;--card2:#1d212a;--line:#2b313d;
--ink:#e8eaf0;--ink2:#a7b0c0;--ink3:#78829a;
--violet:#a78bfa;--green:#34d399;--amber:#fbbf24;--red:#f87171;--cyan:#38bdf8}
@media(prefers-color-scheme:light){:root{--bg:#f6f7f9;--card:#fff;--card2:#f1f3f7;
--line:#dfe3ea;--ink:#12151c;--ink2:#4a5364;--ink3:#6b7488;
--violet:#7c3aed;--green:#059669;--amber:#b45309;--red:#dc2626;--cyan:#0891b2}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:36px 22px 80px}
header{border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:26px}
.eyebrow{font-size:11.5px;letter-spacing:.15em;text-transform:uppercase;color:var(--ink3);font-weight:650}
h1{font-size:30px;margin:8px 0 4px;letter-spacing:-.02em}
.sub{color:var(--ink2);font-size:15px;margin:0}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 13px;font-size:13px;color:var(--ink2)}
.stat b{color:var(--ink);font-weight:660}
.stat.ok{border-color:var(--green)} .stat.warn{border-color:var(--amber)} .stat.bad{border-color:var(--red)}
h2{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink3);
margin:38px 0 12px;font-weight:700;border-top:1px solid var(--line);padding-top:18px}
.q{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--amber);
border-radius:0 11px 11px 0;padding:14px 18px;margin:9px 0}
.q .top{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.q .n{font-size:11px;font-weight:700;color:var(--amber);min-width:20px}
.q .txt{flex:1;min-width:260px;color:var(--ink)}
.q .meta{font-size:11.5px;color:var(--ink3);margin-top:7px}
.q .acts{margin-top:10px;display:flex;gap:6px;flex-wrap:wrap}
.btn{font:600 12px ui-sans-serif,system-ui,sans-serif;padding:5px 11px;border-radius:7px;
border:1px solid var(--line);background:var(--card2);color:var(--ink2)}
.btn.p{border-color:var(--violet);color:var(--violet)}
.tag{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
padding:2px 7px;border-radius:5px;border:1px solid var(--line);color:var(--ink3);white-space:nowrap}
.tag.photo{border-color:var(--cyan);color:var(--cyan)}
.tag.mem{border-color:var(--green);color:var(--green)}
.mem{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--green);
border-radius:0 11px 11px 0;padding:11px 16px;margin:7px 0;font-size:13.5px;color:var(--ink2)}
.mem b{color:var(--ink)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:15px 18px;margin:9px 0}
.card.a{border-left:3px solid var(--green)} .card.b{border-left:3px solid var(--cyan)}
.card.c{border-left:3px solid var(--amber)} .card.refused{border-left:3px solid var(--red)}
.card.skip{opacity:.5}
.card .hd{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.card .id{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;color:var(--ink3)}
.card .idn{font-weight:640;color:var(--ink);flex:1;min-width:220px}
.card .money{font-variant-numeric:tabular-nums;font-weight:700;color:var(--ink);white-space:nowrap}
.card .why{font-size:12px;color:var(--ink3);margin-top:6px}
.card .refuse{color:var(--red);font-size:13px;font-weight:600;margin-top:5px}
.bar{height:5px;background:var(--card2);border-radius:99px;overflow:hidden;margin:14px 0 4px}
.bar>i{display:block;height:100%;background:var(--violet)}
footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);color:var(--ink3);font-size:12.5px;line-height:1.7}
"""


def _tag(text: str, cls: str = "") -> str:
    return f'<span class="tag {cls}">{escape(text)}</span>'


def _question_block(v: CycleView) -> str:
    q = v.queue
    out = []

    if q.auto_answered:
        out.append("<h2>Answered from memory &mdash; not asked</h2>")
        for question, rule in q.auto_answered:
            out.append(
                f'<div class="mem">{_tag("memory", "mem")} '
                f'<b>{escape(rule.answer)}</b> '
                f'<span style="color:var(--ink3)">&mdash; {escape(question.kind.value)} / '
                f'{escape(question.category)}, {len(question.lot_ids)} lot(s), '
                f'learned {escape(rule.learned_cycle)}</span></div>'
            )

    out.append(f"<h2>Needs your eye &mdash; {len(q.asked)} question(s)</h2>")
    if not q.asked:
        out.append('<p style="color:var(--ink2)">Nothing ambiguous this cycle.</p>')
    for i, question in enumerate(q.asked, 1):
        photo = _tag("photo", "photo") if question.wants_photo else ""
        lots = ", ".join(question.lot_ids[:6])
        more = f" +{len(question.lot_ids) - 6}" if len(question.lot_ids) > 6 else ""
        out.append(
            f'<div class="q"><div class="top"><span class="n">{i}</span>'
            f'<span class="txt">{escape(question.prompt)}</span>{photo}</div>'
            f'<div class="meta">{escape(question.kind.value)} &middot; '
            f'{escape(question.category)} &middot; {escape(lots)}{more} &middot; '
            f'impact {question.impact}</div>'
            f'<div class="acts"><button class="btn p">Answer</button>'
            f'<button class="btn">Applies to all {escape(question.category)}</button>'
            f'<button class="btn">Skip</button></div></div>'
        )

    if q.dropped:
        out.append(
            f'<p style="color:var(--ink3);font-size:13px">'
            f'{len(q.dropped)} lower-impact question(s) over the cap. '
            f'{len(q.flagged_lot_ids)} lot(s) ship flagged low-confidence '
            f'rather than blocking the sheet.</p>'
        )
    return "\n".join(out)


_CLS = {Priority.A: "a", Priority.B: "b", Priority.C: "c", Priority.SKIP: "skip"}


def _sheet_block(v: CycleView) -> str:
    out = [f"<h2>The sheet &mdash; {v.summary.allocated} bid(s) allocated</h2>"]
    order = {Priority.A: 0, Priority.B: 1, Priority.C: 2, Priority.SKIP: 3}
    for d in sorted(v.decisions, key=lambda x: (order[x.priority],
                                                -(x.all_in or 0))):
        cls = "refused" if d.needs_human_pricing else _CLS[d.priority]
        caption = v.captions.get(d.lot_id, "")
        money, flag = "", ""
        if d.max_bid is not None:
            money = (f'<span class="money">max ${d.max_bid:,.2f} '
                     f'&middot; all-in ${d.all_in:,.2f}</span>')
            if d.allocated and d.auto_send:
                flag = _tag("auto-send", "mem")
            elif d.allocated:
                flag = _tag("needs approval")
            else:
                flag = _tag("over budget")
        body = (f'<div class="refuse">No external comp &mdash; human pricing required</div>'
                if d.needs_human_pricing else f'<div class="why">{escape(d.reason)}</div>')
        out.append(
            f'<div class="card {cls}"><div class="hd">'
            f'<span class="id">{escape(d.lot_id)}</span>'
            f'<span class="idn">{escape(caption or d.category)}</span>'
            f'{_tag(d.priority.value)}{flag}{money}</div>{body}</div>'
        )
    return "\n".join(out)


def render_console(v: CycleView) -> str:
    s = v.summary
    used = (s.committed_all_in / v.budget_cap * 100) if v.budget_cap else 0
    stats = [
        ("ok" if v.photos_ingested else "", f"<b>{v.photos_ingested}</b> photos ingested"),
        ("", f"<b>{s.total_lots}</b> lots appraised"),
        ("warn" if v.queue.asked else "ok", f"<b>{len(v.queue.asked)}</b> questions"),
        ("ok" if v.queue.auto_answered else "",
         f"<b>{len(v.queue.auto_answered)}</b> from memory"),
        ("", f"<b>{s.allocated}</b> bids &middot; {s.auto_send} auto &middot; "
             f"{s.needs_approval} to approve"),
        ("bad" if s.needs_human_pricing else "",
         f"<b>{s.needs_human_pricing}</b> need pricing"),
    ]
    stat_html = "".join(f'<span class="stat {c}">{t}</span>' for c, t in stats)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Blue Toad Fleet &mdash; {escape(v.cycle_id)}</title>
<style>{_CSS}</style></head><body><div class="wrap">
<header>
  <div class="eyebrow">Blue Toad Fleet &middot; Gate console</div>
  <h1>Cycle {escape(v.cycle_id)}</h1>
  <p class="sub">Sale {escape(v.auction_date)} &middot; absentee cutoff
     {escape(v.deadline)} &middot; budget cap ${v.budget_cap:,.2f} &middot;
     auto-send at or under ${v.auto_send_threshold:,.2f}</p>
  <div class="stats">{stat_html}</div>
  <div class="bar"><i style="width:{min(used, 100):.1f}%"></i></div>
  <div style="font-size:12px;color:var(--ink3)">
    ${s.committed_all_in:,.2f} committed of ${v.budget_cap:,.2f} cap
    ({used:.0f}%)</div>
</header>
{_question_block(v)}
{_sheet_block(v)}
<footer>
  The agent manages its own uncertainty budget: it asks when confidence is low,
  sends without asking when value is low, and needs you less every cycle.<br>
  Unanswered questions do not block &mdash; at the 4PM cutoff the sheet ships with
  those rows flagged low-confidence.
</footer>
</div></body></html>"""
