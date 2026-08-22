# Brief for Claude — spatial, not bidmath. 2026-08-21

Evaluate. Do not implement. This is FYI so you do not "fix" BT-181 on
your side.

The operator walked `fpx2` (BT-002) and `fpx181` (BT-181) side by side.

## Two different facts — do not collapse them

1. **x3 is inside one photo.** Seq 2 shows labelled trays 12 / 14 / 16. That
   is why the `lot_grouping` question was the right question and Bill's
   "x3 bid" is the right ruling. Your mechanic path owns that. Leave it.

2. **BT-181 is not another jewelry table.** It is a close-up of trays 12 and
   14 from seq 2 (cream heart-link, gold mesh, coin-charm bracelet, both
   Christmas trees, white card in the green box). Cropped, 179 frames later.
   Same physical lots. If we bid both, we buy the trays twice.

Your decline of BT-181 stays correct.

## Why grouping missed it — this was predicted

Original spatial rule: the first part of the drop is a linear walk; later
frames get noisier because of late adds and reshoots. This pair is that rule
in photos. If they had asked for a close-up *while still at the table*, it
would be seq 3. It is seq 181, so it is a **return / second pass**, not a
stutter. Embedding already ranked seq 2 as seq 181's #1 neighbour (cos 0.906);
dHash ranked it #94; trajectory attached 181 to uncaptioned seq 180. Sequence
is the walk, not the whole file.

Seq 181 is still in the first 2/3 (cut ~310). Other long-gap recaptions:
Waterford 26→455, sports collectibles 15→404, Topps 1→284. So "last third is
random" is too crude. Linearity decays whenever someone comes back.

## Lot decomposer would not have merged them

Cached appraisals have no `contents`. Even with itemization, contents only
append onto that lot's clerk line. There is no cross-lot contents index.
Overlap would be "Christmas tree pins" vs "rhinestone Christmas tree
brooches" — a human might notice, the agent would not drop 181.

## Lane

Non-adjacent same-category / embedding pass over accepted lots is grok /
intake. Do not add a competing dedup on master. Do not encode 181 into
`mechanic_from_ruling`. If you want a hook from the sheet side (flag two
jewelry lots that share distinctive piece strings), say so and we compose;
do not ship it unilaterally.

Spatial Step 0 is still not on the live path. We are putting those pieces
together on this lane now.
