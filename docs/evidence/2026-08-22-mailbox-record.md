# The Aug 22 cycle's mailbox record — retrieved from the live mailbox

The submission's central narrative — sheet sent, accepted, executed, answered —
rests on one Gmail message that quotes the entire chain inside itself. This
file is that message, retrieved verbatim from the operator's mailbox via the
Gmail API on 2026-08-29 and recorded here so the claim is checkable from the
repository alone. An earlier audit correctly flagged that the message id was
cited in two comp reports but archived nowhere; this closes it.

| | |
|---|---|
| Gmail message id | `1a02b9171cc30d2a` |
| Thread id | `1a0265129c7e6122` |
| Subject | `Re: REVISED Absentee Bids - August 22 Antique & Estate Auction (Bidder: Richmond General)` |
| From | `bluetoadauctionhouse@gmail.com` (Bill & Gina Theesfield, Blue Toad Auctions) |
| To | `beilsco@gmail.com` |
| Date | `2026-08-22T22:22:13Z` (internalDate `1787437333000`) |

The message's own quoted chain carries all three beats:

1. **Sent** — Scott Beilfuss → Blue Toad, Fri Aug 21 2026 4:54 PM CDT: the
   REVISED nine-lot sheet, BT-002 as times-the-money ×3, total line
   `TOTAL COMMITTED PROXY BIDS: $275.00 ($316.25 all-in w/ 15% fee)`.
2. **Accepted** — Bill Theesfield, Fri Aug 21 2026 7:10 PM CDT:
   *"Got it, thanks!"*
3. **Answered** — Bill Theesfield, Sat Aug 22 2026 (22:22Z):
   *"sorry you did not win"*.

## Verbatim plaintext body (as returned by the Gmail API)

```text
sorry you did not win

Bill & Gina Theesfield
Blue Toad Auctions
www.bluetoadauctions.com
847-707-9446

On Fri, Aug 21, 2026 at 7:10 PM Bill Theesfield <
bluetoadauctionhouse@gmail.com> wrote:

> Got it, thanks!
>
>
>
> Bill & Gina Theesfield
> Blue Toad Auctions
> www.bluetoadauctions.com
> 847-707-9446
>
> On Fri, Aug 21, 2026 at 4:54 PM Scott Beilfuss <beilsco@gmail.com> wrote:
>
>> Blue Toad Auctions,
>>
>> This REPLACES my earlier absentee bid list for the Saturday, August 22,
>> 2026 auction
>> at 200 Elizabeth Lane, Genoa City, WI
>> <https://www.google.com/maps/search/200+Elizabeth+Lane,+Genoa+City,+WI?entry=gmail&source=g>.
>> Please disregard the prior sheet.
>>
>> Bill - thank you for confirming the jewelry trays are a x3 bid. I have
>> adjusted
>> accordingly and I am taking all three trays.
>>
>> Bidder Info:
>> Name: Richmond General (Scott)
>> Resale Certificate: On file (Wisconsin Tax-Exempt)
>> Terms: 15% Absentee Buyer Fee acknowledged (Credit Card on File)
>>
>>
>> -----------------------------------------------------------------------------------------
>> 1) [BT-066] Assorted handheld electronic LCD games group lot, including
>> two Excalibur
>> Casino Calculator handhelds, Milton Bradley Electronic Yahtzee, Bonus
>> Poker/Draw Poker, Solitaire, and Radical Video Slot 5000, c. 1990s-2000s.
>> START $5.00 MAX $5.00
>>
>> 2) [BT-235] 1933 Chicago World's Fair 'A Century of Progress' embossed
>> clear glass
>> souvenir bottle with metal cap
>> START $5.00 MAX $10.00
>>
>> 3) [BT-021] Vintage Bell System / Western Electric pink push-button
>> Princess telephone
>> with original printed box
>> START $5.00 MAX $15.00
>>
>> 4) [BT-048] E.T. the Extra-Terrestrial glazed ceramic nightlight/lamp
>> figure, c. 1982
>> START $5.00 MAX $15.00
>>
>> 5) [BT-050] Vintage Lionel metal construction building set in fitted
>> wooden case, circa
>> late 1930s.
>> START $5.00 MAX $15.00
>>
>> 6) [BT-002] ** REVISED - TIMES THE MONEY, TAKING ALL THREE **
>> Estate costume jewelry display trays marked 12, 14, and 16 - gold-tone and
>> silver-tone necklaces, beaded strands, rhinestone and enamel brooches
>> (including Christmas tree pins), bracelets, and wristwatches.
>> Per your confirmation (Bill, 8/21) this lot sells x3 the money.
>> START $5.00 MAX $25.00 PER TRAY x 3 TRAYS = $75.00 TOTAL
>> >> I am taking ALL THREE trays. Please do NOT limit me to one unit on
>> this lot. <<
>>
>> 7) [BT-041] Lot of Edison phonograph cylinder records and cardboard
>> containers, including
>> Edison Gold Moulded Record and Blue Amberol Record tubes, Thomas A.
>> Edison,
>> Inc., early 20th century.
>> START $5.00 MAX $25.00
>>
>> 8) [BT-087] Bulk lot of assorted vintage and modern costume jewelry,
>> including faux
>> pearls, beaded necklaces, brooches, and novelty pins in a clear plastic
>> tote
>> START $5.00 MAX $15.00 (revised down from $25.00)
>>
>> 9) [BT-001] Collection of 12 vintage Topps sports trading cards (10
>> baseball, 2 football)
>> dating from 1956 to 1962, featuring major stars and Hall of Famers
>> including
>> Mickey Mantle, Willie Mays, Sandy Koufax, Yogi Berra, Roberto Clemente,
>> Roger
>> Maris, Bart Starr, and Paul Hornung.
>> START $35.00 MAX $100.00
>>
>>
>> -----------------------------------------------------------------------------------------
>> TOTAL COMMITTED PROXY BIDS: $275.00 ($316.25 all-in w/ 15% fee)
>>
>> Special Instructions:
>> - BT-002 is the ONE exception to my usual one-unit rule: take all three
>> trays at x3.
>> - For any OTHER 'Buyer's Choice / Times the Money' shelf lot, max
>> quantity is 1 unit.
>> - Standard $5.00 bidding increments applied.
>> - Please confirm receipt of this REVISED sheet by reply email.
>>
>> Thank you,
>>
>> --
>> Scott Beilfuss
>> Richmond General
>>
>
```

Retrieval provenance: Gmail API `get_message` on id `1a02b9171cc30d2a`,
2026-08-29, from the operator's own account; the block above is the API's
`plaintextBody` field unmodified. A curated record was chosen over a raw
`.eml` deliberately — full RFC headers add routing metadata to a public
repository without adding evidentiary value; the id, thread id, timestamps,
and verbatim body are what the cited claims rest on.

---

# The ×3 confirmation — the auctioneer's own words, in the earlier thread

The narrative's remaining gap was Bill's literal confirmation, which NOTES.md
cites to "email 2026-08-21 21:43 UTC" without an archived artifact. That message
lives in a separate, earlier thread than the one above — the operator's
pre-submission question about the jewelry trays. Retrieved verbatim from the
mailbox via the Gmail API on 2026-08-29 and recorded here; the timestamp matches
the NOTES.md citation to the minute.

| | |
|---|---|
| Gmail message id | `1a026475c2a03ae2` |
| Thread id | `1a026396d37c5e51` |
| Subject | `Re: Question on 2nd picture 8/22 auction` |
| From | `bluetoadauctionhouse@gmail.com` (Bill & Gina Theesfield, Blue Toad Auctions) |
| To | `beilsco@gmail.com` |
| Date | `2026-08-21T21:43:12Z` (internalDate `1787348592000`) |
| In reply to | Scott's question, sent `2026-08-21T21:31:55Z` (message `1a0263cd46eb404c`) |

The reply quotes the question inside itself, so one message carries both beats:
the operator asking whether the trays sell ×3, and the auctioneer confirming.
Eleven minutes after this confirmation, the REVISED sheet (archived above) went
out carrying the ×3 ruling.

## Verbatim plaintext body (as returned by the Gmail API)

```text
Yes, that is a x3 bid.

Thank you

Bill & Gina Theesfield
Blue Toad Auctions
www.bluetoadauctions.com
847-707-9446

On Fri, Aug 21, 2026 at 4:32 PM Scott Beilfuss <beilsco@gmail.com> wrote:

> The Assorted lot of vintage and modern estate costume jewelry including
> goldtone
> and silver-tone necklaces, beaded strands, rhinestone and enamel
> brooches (including Christmas tree pins), bracelets, and wristwatches
> across multiple trays marked 12, 14, and 16.
>
> Is that a x3 at bid?
>
> I'm submitting some prebids and would like to include this lot.
>
> Thanks You,
>
> --
> Scott Beilfuss
> Richmond General
>
```

Retrieval provenance: Gmail API `get_message` on id `1a026475c2a03ae2`,
2026-08-29, from the operator's own account; the block above is the API's
`plaintextBody` field unmodified. With this thread archived, the full BT-002
loop is artifact-backed end to end: the model's disambiguation question
(`data/aug22_gallery_4160518/appraisal_results.json`, lot BT-002) → the
operator's question (21:31Z) → the auctioneer's "Yes, that is a x3 bid"
(21:43Z) → the REVISED sheet (21:54Z, above) → "Got it, thanks!" (00:10Z) →
"sorry you did not win" (22:22Z).
