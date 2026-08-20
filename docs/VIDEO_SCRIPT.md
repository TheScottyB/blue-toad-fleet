# Blue Toad Fleet — 4:00 Demo Narration

Voice: the shop owner, not the engineer. Plain, grounded, a little tired of the problem.
Pace target ~150 wpm. Total ~590 words. Timecodes are targets, not hard cuts.

---

## BEAT 1 — 0:00–0:45 · The 450-photo problem
**On screen:** Raw auction gallery page → wall of unlabelled photos → calendar hitting Friday 8:00 PM.

> I run a one-person resale shop in Richmond, Illinois.
>
> Two point three miles north, across the Wisconsin line in Genoa City, there's an auction
> house called Blue Toad. Every two weeks they drop a single web page with four hundred and
> fifty photographs on it. No lot numbers. No catalog. No descriptions. Just photos of an
> estate, and a pile of SEO keywords.
>
> Absentee bids are due Friday at eight. To bid, I have to click through all four hundred
> and fifty, work out what things are, find comps, do the margin math, and write the email —
> while I'm running the register.
>
> So every cycle went one of two ways. I'd drive up Saturday morning for the one-hour
> preview and come home with a three-hundred-dollar truckload of junk that takes a year to
> clear. Or I'd miss the sale.
>
> Money was never the problem. Looking at four hundred and fifty photos was the problem.

## BEAT 2 — 0:45–1:45 · Multimodal distillation
**On screen:** Terminal running `make demo` → photos collapsing into lots → spatial room graph drawing itself.

> Blue Toad Fleet is the thing I built to look at them for me.
>
> Every photo goes through two tiers on Vertex AI. Gemini 3.5 Flash Lite triages the gallery
> cheaply — what is this, is it worth a second look. What survives goes to Gemini 3.6 Flash
> for real appraisal against a structured schema: maker, period, condition, comps.
>
> But the part that actually made this work isn't the model. It's the room.
>
> An auctioneer doesn't teleport. He walks a pole barn, table by table. So the agent reads
> the background — blue pleated vinyl on the side tables, raw pine on the islands, bare
> concrete under them — and rebuilds the floor plan from the surfaces. It reads the edge of
> each frame for slivers of neighboring items, and follows the walking path.
>
> On the July gallery, that collapsed ninety-five duplicate camera angles into single lots,
> and merged ten loose under-table box photos into one dinnerware set. Not ten blind bids.
> One.

## BEAT 3 — 1:45–2:45 · The Gate Console and the pushback
**On screen:** Live Gate Console → memory rows → curator challenge → the sheet.

> Then it hands the judgment back to me.
>
> This is the gate console. Four hundred sixty-two photos in. Three hundred fifty-nine lots
> appraised. Twelve bids out — ten it sends on its own, two it wants me to look at.
>
> It doesn't ask me everything. Three questions this cycle it answered from memory, because
> I already told it last time that I've got no room for dishes and a backlog of unlisted
> tools.
>
> And when it doesn't know, it says so. On unmarked pottery it writes "no external comp,
> human pricing required," instead of inventing a number. Refusing to guess is the feature.
>
> It also argues with me. I told it to drop sports cards. It came back and said: understood
> on the modern stuff, but photo one is thirteen Golden Era Topps cards in top-loaders,
> those turn in under two weeks — keep a hundred-dollar defensive cap.
>
> That's not a chatbot. That's a buyer.

## BEAT 4 — 2:45–3:45 · Running on Google Cloud
**On screen:** Cloud Run service page → revision + region → Vertex AI request logs → `/health` 200 → `make test`.

> All of it runs on Google Cloud.
>
> One container on Cloud Run in us-central-one, serving the console, the sourcing API, and a
> health endpoint you can hit right now. Vertex AI handles the model routing, with structured
> output schemas so appraisals come back as data, not prose.
>
> The bidding math never touches a model. Margin target, condition discounts, five-dollar
> increments, the fifteen percent absentee fee — that's plain Python, covered by a hundred
> and sixty unit tests that run in under a tenth of a second.
>
> On the July gallery, the old unconstrained wishlist came to fourteen thousand three
> hundred forty dollars. The agent brought that down to nineteen hundred fifteen — inside
> the cap.

## BEAT 5 — 3:45–4:00 · Close
**On screen:** The sheet, then closing card.

> I'm not trying to take myself out of the loop. I'm one person who needs the eyes of five.
>
> Blue Toad Fleet reads the room, prices what it can, admits what it can't, and hands me ten
> lots that make money. That's the whole thing.
