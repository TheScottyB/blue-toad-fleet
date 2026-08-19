# The Broker — design, written before the code

A judge who opens the repo will check whether "scoped, short-lived, revocable
grants" is a design or a slogan. This is the design. If the implementation
drifts from it, the README claim comes out.

## What it is not

Not a secret-fetching helper. If agents called a service that handed back a
Gmail refresh token, that would be a secret fetch with extra steps and should
be described as such.

## What it is

A credential proxy. The Broker is the only principal with IAM access to Secret
Manager. Agents never receive an upstream token — they receive a *grant*, and
the Broker performs the outbound call on their behalf.

## Flow

1. Agent calls the Broker with its **Cloud Run service-identity ID token**
   (Google-signed, verifiable from Google's JWKS — we are not inventing an
   identity system, we are layering delegation onto one).
2. Broker checks a Firestore **policy table**: `agent -> permitted (action, target)`.
3. Broker mints a **grant**: a JWT signed with a key held in Cloud KMS.

   ```json
   {
     "agent":  "bidder@<project>.iam.gserviceaccount.com",
     "action": "gmail.draft",
     "target": "to=info@bluetoadauctions.com",
     "cycle":  "2026-08-22",
     "exp":    "<= issue + 10 minutes>",
     "jti":    "<uuid>"
   }
   ```

4. Agent presents the grant. Broker verifies signature, expiry, and that `jti`
   is **not on the Firestore denylist**, then makes the Gmail/eBay/Slack call
   itself and returns the result.
5. Every issuance and every use is logged with the Cloud Trace id.

## Properties, and their honest bounds

| Property | How | Bound |
|---|---|---|
| Scoped | action + target constraint checked at use, not just issue | Only as good as the policy table |
| Short-lived | `exp` <= 10 min | Clock skew tolerance ±30s |
| Revocable | `jti` denylist checked per call | Takes effect on the **next call**, not mid-flight |
| Attributable | agent identity + trace id on every log line | Broker is trusted; it signs its own audit |
| No agent-held secrets | agents get grants, never upstream tokens | The Broker itself holds everything — it is the crown jewel |

## What this does not do

It does not make the Broker unnecessary to trust. Compromise the Broker and
you have every token. The gain over agents-hold-tokens is blast radius,
expiry, revocation, and a single audited choke point — not the elimination of
a trusted component. Say this in the video rather than letting a judge find it.
