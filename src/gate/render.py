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
from src.bidmath import (units_committed, clerk_directive, BidMechanic,
                         Decision, Priority, SheetSummary)
from src.gate.voice import PitchVoice
from src.intake.spatial import Seat, Zone
from src.memory.ids import make_question_id


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
    illustrative: bool = False
    lots_total: int | None = None
    voice: PitchVoice | None = None
    seats: list[Seat] = field(default_factory=list)


_CSS = """
:root{--bg:#0f1115;--card:#171a21;--card2:#1d212a;--line:#2b313d;
--ink:#e8eaf0;--ink2:#a7b0c0;--ink3:#78829a;
--violet:#a78bfa;--green:#34d399;--amber:#fbbf24;--red:#f87171;--cyan:#38bdf8;
color-scheme: dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:36px 22px 80px}
header{border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:26px}
.eyebrow{font-size:11.5px;letter-spacing:.15em;text-transform:uppercase;color:var(--ink3);font-weight:650}
h1{font-size:32px;margin:8px 0 4px;letter-spacing:-.02em}
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
.btn{font:600 12px ui-sans-serif,system-ui,sans-serif;padding:6px 13px;border-radius:7px;
border:1px solid var(--line);background:var(--card2);color:var(--ink2);cursor:pointer;transition:all .15s}
.btn:hover{background:var(--line);color:var(--ink)}
.btn.p{border-color:var(--violet);color:var(--violet)}
.answer-text{width:100%;margin-top:8px;padding:7px 9px;border-radius:7px;
border:1px solid var(--line);background:var(--card2);color:var(--ink);
font:13px ui-sans-serif,system-ui,sans-serif}
#answer-result{margin:10px 0;padding:10px 14px;border-radius:8px;
border:1px solid var(--green);color:var(--green);font-size:13px}
.tag{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
padding:2px 7px;border-radius:5px;border:1px solid var(--line);color:var(--ink3);white-space:nowrap}
.tag.photo{border-color:var(--cyan);color:var(--cyan)}
.tag.mem{border-color:var(--green);color:var(--green)}
.defer{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--ink3);
border-radius:0 11px 11px 0;padding:11px 16px;margin:7px 0;opacity:.72}
.defer .txt{color:var(--ink2);font-size:13.5px}
.defer .meta{font-size:11.5px;color:var(--ink3);margin-top:5px}
.mem{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--green);
border-radius:0 11px 11px 0;padding:11px 16px;margin:7px 0;font-size:13.5px;color:var(--ink2)}
.mem b{color:var(--ink)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:15px 18px;margin:9px 0;transition:transform .1s}
.card:hover{border-color:var(--ink3)}
.card.a{border-left:3px solid var(--green)} .card.b{border-left:3px solid var(--cyan)}
.card.c{border-left:3px solid var(--amber)} .card.refused{border-left:3px solid var(--red)}
.card.skip{opacity:.5}
.card .hd{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.card .id{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;color:var(--ink3)}
.card .idn{font-weight:640;color:var(--ink);flex:1;min-width:220px}
.card .money{font-variant-numeric:tabular-nums;font-weight:700;color:var(--ink);white-space:nowrap}
.card .why{font-size:12px;color:var(--ink3);margin-top:6px}
.card .refuse{color:var(--red);font-size:13px;font-weight:600;margin-top:5px}
.bar{height:6px;background:var(--card2);border-radius:99px;overflow:hidden;margin:14px 0 4px}
.bar>i{display:block;height:100%;background:var(--violet)}
footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);color:var(--ink3);font-size:12.5px;line-height:1.7}

/* 2D Showroom Map */
.map-container{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin:22px 0}
.map-title{font-size:13px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--cyan);margin-bottom:14px;display:flex;justify-content:space-between}
.map-grid{display:grid;grid-template-columns:1fr 1.6fr 1fr;grid-template-rows:auto auto auto;gap:12px}
.map-zone{background:var(--card2);border:1px dashed var(--line);border-radius:8px;padding:12px;font-size:12px;color:var(--ink2);transition:all .2s}
.map-zone:hover{border-color:var(--cyan);background:var(--card)}
.map-zone.wall{grid-column:1 / span 3;text-align:center;border-style:solid;border-color:var(--line);background:var(--card2)}
.map-zone.aisle{grid-column:2;background:rgba(167,139,250,0.06);border-color:var(--violet);text-align:center}
.map-zone b{color:var(--ink);display:block;font-size:13px;margin-bottom:3px}
.directive{margin-top:6px;padding:6px 8px;border-left:2px solid var(--cyan);background:rgba(56,189,248,0.06);font-size:12px;color:var(--ink);line-height:1.45}
.map-tag{font-size:10px;padding:2px 6px;border-radius:4px;background:rgba(56,189,248,0.15);color:var(--cyan);font-weight:600}
.seat-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;align-items:flex-start}
.seat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px;min-width:72px}
.seat b{display:block;color:var(--ink);font-size:12px;margin-bottom:4px}
.thumb{display:inline-block;font:600 10px ui-monospace,Menlo,monospace;letter-spacing:.02em;
padding:2px 6px;margin:2px 3px 0 0;border-radius:4px;background:rgba(56,189,248,.15);color:var(--cyan)}
.holding{margin-top:16px;padding-top:12px;border-top:1px dashed var(--line)}
.holding .map-title{margin-bottom:10px}

/* Pitch Banner */
.pitch-card{background:linear-gradient(135deg, rgba(167,139,250,0.08) 0%, rgba(56,189,248,0.08) 100%);
border:1px solid var(--violet);border-radius:12px;padding:18px;margin:20px 0}
.pitch-hd{font-weight:700;font-size:14px;color:var(--violet);margin-bottom:8px;display:flex;align-items:center;gap:8px}
"""

_ANSWER_JS = """
<script>
(function(){
  var box = document.getElementById("answer-result");
  var tokenEl = document.getElementById("op-token");
  if (tokenEl) tokenEl.value = sessionStorage.getItem("opToken") || "";
  document.addEventListener("click", function(ev){
    var btn = ev.target.closest("[data-act=answer]");
    if (!btn) return;
    ev.preventDefault();
    var card = btn.closest(".q");
    if (!card) return;
    var qid = card.getAttribute("data-question-id");
    var input = card.querySelector(".answer-text");
    var answer = ((input && input.value) || "").trim()
      || (btn.getAttribute("data-answer") || "").trim();
    if (!answer) { if (input) input.focus(); return; }
    btn.disabled = true;
    var label = btn.textContent;
    btn.textContent = "saving…";
    if (box) { box.hidden = false; box.textContent = "saving…"; }
    var headers = {"Content-Type": "application/json"};
    var tokenEl = document.getElementById("op-token");
    var token = (tokenEl && tokenEl.value) || sessionStorage.getItem("opToken") || "";
    if (tokenEl && tokenEl.value) sessionStorage.setItem("opToken", tokenEl.value);
    if (token) headers["X-Operator-Token"] = token;
    fetch("/api/answer", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({question_id: qid, answer: answer})
    }).then(function(r){
      return r.json().then(function(j){ return {ok: r.ok, j: j}; });
    }).then(function(x){
      if (box) {
        box.textContent = x.ok
          ? (x.j.status + " · " + ((x.j.rule && x.j.rule.answer) || x.j.reason || "recorded"))
          : (x.j.detail || "failed");
      }
      if (x.ok) setTimeout(function(){ location.reload(); }, 700);
      else { btn.disabled = false; btn.textContent = label; }
    }).catch(function(){
      btn.disabled = false;
      btn.textContent = label;
      if (box) box.textContent = "network error";
    });
  });
})();
</script>
"""


def _tag(text: str, cls: str = "") -> str:
    return f'<span class="tag {cls}">{escape(text)}</span>'


def _seq_chip(photo_id: str) -> str:
    return (
        f'<span class="thumb" data-photo-id="{escape(photo_id)}">'
        f'{escape(photo_id[-7:])}</span>'
    )


def _seat_html(s: Seat) -> str:
    thumbs = "".join(_seq_chip(p) for p in s.photo_ids)
    return (
        f'<div class="seat"><b>{escape(s.lot_id)}</b>{thumbs}</div>'
    )


def _row_for(v: CycleView | None, zone: Zone) -> str:
    if not v:
        return ""
    seats = [s for s in v.seats if s.zone == zone]
    seats.sort(key=lambda s: s.walk_index)
    if not seats:
        return ""
    return (
        '<div class="seat-row">'
        + "".join(_seat_html(s) for s in seats)
        + "</div>"
    )


def _holding_strip(v: CycleView | None) -> str:
    if not v:
        return ""
    unplaced = [s for s in v.seats if s.zone is Zone.UNKNOWN]
    if not unplaced:
        return ""
    unplaced.sort(key=lambda s: s.walk_index)
    body = "".join(_seat_html(s) for s in unplaced)
    return (
        '<div class="holding" id="unplaced">'
        '<div class="map-title">Not yet placed</div>'
        f'<div class="seat-row">{body}</div></div>'
    )


def _map_block(v: CycleView | None = None) -> str:
    return f"""
<div class="map-container">
  <div class="map-title">
    <span>Pole Barn Showroom Topology &middot; 200 Elizabeth Lane, Genoa City</span>
    <span class="map-tag">Invariant Spatial Graph</span>
  </div>
  <div class="map-grid">
    <div class="map-zone wall">
      <b>NORTH BACK WALL &middot; HANGING DISPLAYS</b>
      <span>Framed advertising signs, lighted beer signs, vintage travel posters</span>
      {_row_for(v, Zone.NORTH_BACK_WALL)}
    </div>
    <div class="map-zone">
      <b>WEST SIDE TABLES (A & B)</b>
      <span>Glassware, Princess phones, small electronics, collectibles</span>
      {_row_for(v, Zone.WEST_SIDE_TABLES)}
    </div>
    <div class="map-zone aisle">
      <b>=== CENTER AISLE & AUCTIONEER PODIUM ===</b>
      <div style="margin-top:6px;font-size:11.5px;color:var(--violet)">
        <b>Island Table 1:</b>
        {_row_for(v, Zone.CENTER_ISLAND_1)}
        <b>Island Table 2:</b>
        {_row_for(v, Zone.CENTER_ISLAND_2)}
      </div>
    </div>
    <div class="map-zone">
      <b>EAST SIDE TABLES (C & D)</b>
      <span>Stoneware crocks, vintage tools, railroadiana</span>
      {_row_for(v, Zone.EAST_SIDE_TABLES)}
    </div>
    <div class="map-zone wall" style="background:rgba(0,0,0,0.2)">
      <b>SOUTH STANDING ROOM & UNDER-TABLE STORAGE</b>
      <span>Concrete floor multi-box dinnerware runs (Poppy Trail) &middot; Cashier cage & refreshments</span>
      {_row_for(v, Zone.SOUTH_UNDER_TABLE)}
    </div>
  </div>
  {_holding_strip(v)}
</div>
"""


def _pitch_block(pitch_text: str = "", voice: PitchVoice | None = None) -> str:
    """
    The curator's read on the sheet, in prose.

    Structured PitchVoice (preferred) badges whether Gemma or the template
    wrote it. A free-text pitch_text is the master's single-paragraph fallback.
    Invented figures never reach here — write_pitch_voice / curator_voice
    already discarded them.
    """
    if voice is not None and not voice.fallback:
        badge = "template fallback" if voice.fallback else "Gemma 4 · Vertex AI"
        push = (f"<br><b>Pushback:</b> {escape(voice.pushback)}"
                if voice.pushback else "")
        body = (
            f"<b>Top 3 Alpha Picks:</b> {escape(voice.alpha)}<br>"
            f"<b>Fast Smalls:</b> {escape(voice.fast_smalls)}<br>"
            f"<b>Wildcard / ruled out:</b> {escape(voice.wildcard)}"
            f"{push}"
        )
        return f"""
<div class="pitch-card">
  <div class="pitch-hd">
    Curator&rsquo;s read
    <span class="tag" style="margin-left:auto;border-color:var(--violet);color:var(--violet)">{escape(badge)}</span>
  </div>
  <div style="font-size:13.5px;color:var(--ink2);line-height:1.65">{body}</div>
  <div style="font-size:11px;color:var(--ink3);margin-top:9px">
    Prose only. Lots and bids are set by the deterministic sheet; figures
    are validated against it before display.
  </div>
</div>
"""
    if not pitch_text:
        return ""
    return f"""
<div class="pitch-card">
  <div class="pitch-hd">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
    Curator&rsquo;s read
    <span class="tag" style="margin-left:auto;border-color:var(--violet);color:var(--violet)">Gemma 4 &middot; Vertex AI</span>
  </div>
  <div style="font-size:13.5px;color:var(--ink2);line-height:1.65">{escape(pitch_text)}</div>
  <div style="font-size:11px;color:var(--ink3);margin-top:9px">
    Prose only. Lots and bids are set by the deterministic sheet above; figures
    are validated against it before display.
  </div>
</div>
"""



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
    out.append('<div id="answer-result" hidden></div>')
    if not q.asked:
        # Only say it when it is true. With work still deferred to the preview,
        # "nothing ambiguous" is the console overclaiming on the operator's behalf.
        out.append('<p style="color:var(--ink2)">'
                   + ("Nothing left for the desk &mdash; see below."
                      if q.deferred else "Nothing ambiguous this cycle.")
                   + '</p>')
    for i, question in enumerate(q.asked, 1):
        photo = _tag("photo", "photo") if question.wants_photo else ""
        lots = ", ".join(question.lot_ids[:6])
        more = f" +{len(question.lot_ids) - 6}" if len(question.lot_ids) > 6 else ""
        qid = make_question_id(v.cycle_id, question)
        out.append(
            f'<div class="q" data-question-id="{escape(qid)}">'
            f'<div class="top"><span class="n">{i}</span>'
            f'<span class="txt">{escape(question.prompt)}</span>{photo}</div>'
            f'<div class="meta">{escape(question.kind.value)} &middot; '
            f'{escape(question.category)} &middot; {escape(lots)}{more} &middot; '
            f'impact {question.impact}</div>'
            f'<textarea class="answer-text" rows="2" '
            f'placeholder="Type the standing answer, then Answer"></textarea>'
            f'<div class="acts">'
            f'<button type="button" class="btn p" data-act="answer">Answer</button>'
            f'<button type="button" class="btn" data-act="answer" '
            f'data-answer="Applies to all {escape(question.category)}">'
            f'Applies to all {escape(question.category)}</button>'
            f'</div></div>'
        )

    if q.deferred:
        out.append(
            f"<h2>Needs the item in hand &mdash; not asked before the cutoff "
            f"({len(q.deferred)})</h2>"
        )
        out.append(
            '<p style="color:var(--ink3);font-size:13px;margin:-4px 0 10px">'
            'Marks and condition cannot be settled from a gallery photo at any '
            'resolution. These wait for Saturday&rsquo;s preview; their lots ship '
            'flagged rather than blocking the sheet.</p>'
        )
        for question in q.deferred:
            lots = ", ".join(question.lot_ids[:6])
            more = f" +{len(question.lot_ids) - 6}" if len(question.lot_ids) > 6 else ""
            out.append(
                f'<div class="defer"><div class="txt">{escape(question.prompt)}</div>'
                f'<div class="meta">{escape(question.kind.value)} &middot; '
                f'{escape(question.category)} &middot; {escape(lots)}{more}</div></div>'
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
                                                -(x.committed_all_in or 0))):
        cls = "refused" if d.needs_human_pricing else _CLS[d.priority]
        caption = v.captions.get(d.lot_id, "")
        money, flag = "", ""
        if d.max_bid is not None:
            # A card reading "all-in $28.75" for an $86.25 commitment is what
            # the operator approves against, on a page whose own header says
            # $327.75. Show the commitment whenever it differs from one unit.
            _units = units_committed(d.mechanic, d.unit_count, d.units_wanted)
            if _units > 1:
                money = (f'<span class="money">max ${d.max_bid:,.2f}/unit '
                         f'&times;{_units} &middot; committed '
                         f'${d.committed_max:,.2f} &middot; all-in '
                         f'${d.committed_all_in:,.2f}</span>')
            else:
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
        # The one line that says what to DO with this lot. It lived in bidmath
        # with no caller outside its own tests — built, tested, and wired to
        # nothing — while the surface the operator actually reads showed a price
        # and no instruction. Rendered as prose in its own class so the card's
        # money figures remain the only summable ones on the page: the header
        # and the cards have to keep reconciling.
        directive = (f'<div class="directive">{escape(clerk_directive(d))}</div>'
                     if (d.mechanic is not BidMechanic.STRAIGHT
                         or d.needs_mechanic_ruling) else "")
        alloc = "1" if d.allocated else "0"
        out.append(
            f'<div class="card {cls}" data-allocated="{alloc}"><div class="hd">'
            f'<span class="id">{escape(d.lot_id)}</span>'
            f'<span class="idn">{escape(caption or d.category)}</span>'
            f'{_tag(d.priority.value)}{flag}{money}</div>{body}{directive}</div>'
        )
    return "\n".join(out)


def render_console(v: CycleView, pitch_text: str = "") -> str:
    s = v.summary
    of_total = f" of {v.lots_total}" if v.lots_total else ""
    used = (s.committed_all_in / v.budget_cap * 100) if v.budget_cap else 0
    stats = [
        ("ok" if v.photos_ingested else "", f"<b>{v.photos_ingested}</b> photos ingested"),
        ("", f"<b>{s.total_lots}</b>{of_total} lots appraised"),
        ("warn" if v.queue.asked else "ok", f"<b>{len(v.queue.asked)}</b> questions"),
        ("ok" if v.queue.auto_answered else "",
         f"<b>{len(v.queue.auto_answered)}</b> from memory"),
        ("", f"<b>{s.allocated}</b> bids &middot; {s.auto_send} auto &middot; "
             f"{s.needs_approval} to approve"),
        ("bad" if s.needs_human_pricing else "",
         f"<b>{s.needs_human_pricing}</b> need pricing"),
    ]
    stat_html = "".join(f'<span class="stat {c}">{t}</span>' for c, t in stats)

    banner = (
        '<div style="background:var(--card);border:1px solid var(--amber);'
        'border-radius:10px;padding:10px 14px;margin-bottom:16px;font-size:13px;'
        'color:var(--amber)"><b>Illustrative cycle.</b> Seeded appraisals and '
        'comps; the decision code, ranking and memory are real.</div>'
        if v.illustrative else "")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Blue Toad Fleet &mdash; {escape(v.cycle_id)}</title>
<style>{_CSS}</style></head><body><div class="wrap">
<header>
  {banner}
  <div class="eyebrow">Blue Toad Fleet &middot; Gate console
    <label style="float:right;font-size:11px;color:var(--ink3);font-weight:500;letter-spacing:0">
      operator key
      <input id="op-token" type="password" autocomplete="off"
        style="margin-left:6px;padding:3px 7px;border-radius:5px;border:1px solid var(--line);background:var(--card2);color:var(--ink)">
    </label>
  </div>
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
{_map_block(v)}
{_pitch_block(pitch_text, v.voice)}
{_question_block(v)}
{_sheet_block(v)}
<footer>
  The agent manages its own uncertainty budget: it asks when confidence is low,
  sends without asking when value is low, and needs you less every cycle.<br>
  Unanswered questions do not block &mdash; at the Friday 8:00 PM cutoff the sheet ships with
  those rows flagged low-confidence.
</footer>
</div>
{_ANSWER_JS}
</body></html>"""
