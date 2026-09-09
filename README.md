# AI Agent Convo — WhatsApp Clinic Assistant

A WhatsApp bot for a (fictional) clinic that answers questions from a small
knowledge file, books/checks/cancels appointments against MongoDB with
tappable buttons and lists, hands off to a human on request, and replies in
English, Hinglish, or Telugu depending on how the user writes.

## Status

Code for all 6 build phases is written and unit-tested (40 tests, see
`tests/`). **Not deployed, not yet run against a live WhatsApp number** —
that needs your Meta/Gemini/MongoDB accounts and is a separate step (see
"Going live" below). `.github/workflows/deploy.yml` exists but is inert
until its placeholders are filled in and the private key is added.

## Architecture

```
WhatsApp ──POST /webhook──▶ FastAPI (app/main.py)
                                │  verify X-Hub-Signature-256, parse, LPUSH
                                ▼
                          Redis "incoming_queue"
                                │  BRPOP
                                ▼
                        workers/queue.py (separate process)
                                │
             ┌──────────────────┼───────────────────┐
             ▼                  ▼                    ▼
       dedupe (Redis)   session (Redis)      Gemini agent loop
                          history/lang/                │  tools ↓
                          handoff flag         MongoDB (doctors, slots,
                                                appointments, conversations)
                                │
                                ▼
                    WhatsApp send (text / buttons / list)
```

The webhook returns 200 as fast as possible — verify, parse, push, done —
because Meta retries a slow or non-200 delivery. Everything that can be slow
or fail (Gemini, Mongo, the outgoing WhatsApp call) happens in the worker,
which is why it's a second process instead of a `BackgroundTask`: a crash
mid-message doesn't lose the message (it's already off the queue and Meta
already got its 200, but dedupe + the worker's own retry-on-restart mean a
redelivered webhook is still handled correctly) and the worker scales
independently of the web process.

## Tools the agent can call

| Tool | Does |
|---|---|
| `get_clinic_info(topic)` | Timings, location, doctors, services, parking, insurance, payment methods |
| `list_doctors()` | All doctors, speciality, fee — rendered as a WhatsApp list |
| `list_available_slots(doctor_id, date)` | Open slot times for a doctor/date — rendered as a WhatsApp list |
| `book_appointment(doctor_id, date, time, patient_name)` | **Intercepted** — see below, doesn't book directly |
| `get_my_appointments()` | This phone number's upcoming bookings |
| `cancel_appointment(appointment_id)` | Cancels and frees the slot |
| `request_human_handoff(reason)` | Silences the bot for this number, alerts staff |

`book_appointment` is special: when the model calls it, `agent/loop.py`
doesn't execute it. It stores the proposed booking on the session and tells
`workers/queue.py` to send a **Confirm/Cancel button** message instead. Only
a tapped "Confirm" actually calls the real booking function. This is
deliberate — it's the one action in this bot that costs money and can't be
undone by re-asking, so it doesn't go through free-text-to-tool-call without
a deterministic UI checkpoint in between. It also matches why buttons/lists
are used instead of free text generally: fewer parsing errors, a clearer
choice for the user, and it skips a whole model round-trip for something a
tap can settle directly (cheaper in tokens, not just nicer UX).

## Retries, dedupe, and double-booking

- **Dedupe**: `SETNX msg:{wamid}` in Redis, 24h TTL. The wamid (WhatsApp
  message id) is unique per message, so this is correct even across Meta's
  retries — the webhook queues every delivery it gets signed correctly,
  and the worker is where a repeat gets silently dropped (see
  `test_worker.py::test_duplicate_message_is_processed_once`).
- **Outgoing send retries**: 3 attempts, backoff 1s/2s/4s, in
  `whatsapp/client.py`.
- **Double-booking**: a single atomic `find_one_and_update({..., booked:
  False}, {"$set": {"booked": True}})` claims a slot. There is no
  read-then-write anywhere in the booking path — two people tapping Confirm
  on the same slot in the same second cannot both get it (see
  `tests/test_bookings.py::test_double_booking_the_same_slot_is_rejected`).

## Human handoff

"talk to a human"/"agent" in free text, or the model calling
`request_human_handoff`, sets a `handoff` flag on the Redis session. While
set, the worker stores incoming messages (so staff can see what was said)
but never runs the agent or replies. `POST /admin/release/{phone}` (with
header `X-Admin-Token`) clears the flag and hands the conversation back to
the bot. Staff get a WhatsApp text to `STAFF_PHONE` with the reason and the
last 5 messages the moment handoff triggers.

## Language handling

A tiny Gemini call classifies each **text** message (not button/list taps,
which aren't language-bearing) as `en` / `hinglish` / `te`, cached on the
session for 10 messages so the bot isn't spending a model call per message
just to re-confirm what it already knows. The system prompt tells the model
to reply in that language *and script* — Hinglish stays in Roman script
(mixing scripts reads as broken to users), Telugu gets Telugu script. Button
and list labels are pulled from a small per-language dict
(`agent/prompts.py::UI_TEXT`) rather than translated live, so the UI text is
consistent and doesn't cost a model call.

## Cost tracking

Every Gemini response's `usage_metadata` (prompt/completion tokens) is
accumulated per phone number in Mongo's `conversations` collection, priced
against `services/costs.py::PRICE_PER_MILLION_TOKENS_USD` — **verify that
table against Gemini's current pricing page before trusting the dollar
figures**; the mechanism is what matters, and update the table when you
check. `GET /admin/conversations/{phone}` (with `X-Admin-Token`) returns the
running total alongside history and bookings.

<!-- TODO once deployed: screenshot of a real conversation's cost here -->
<!-- TODO once deployed: short GIF of a booking flow on WhatsApp here -->

## Running it locally

Prerequisites this session couldn't install for you (no passwordless sudo,
no Docker daemon in this sandbox):

```bash
sudo apt install -y redis-server     # or point REDIS_URL at any reachable Redis
```

MongoDB: use a free [Atlas](https://www.mongodb.com/cloud/atlas/register)
cluster — no local install needed either way.

```bash
cp .env.example .env        # fill in MONGODB_URI at minimum to run tests against real data
uv sync                     # installs into .venv, including dev/test deps
uv run python scripts/seed.py       # 3 doctors + 7 days of slots
uv run pytest -q                    # 40 tests, no live credentials required

# two processes, two terminals:
uv run uvicorn app.main:app --reload
uv run python -m workers.queue
```

To actually receive WhatsApp messages you need a public HTTPS URL pointing
at your local `/webhook`. `ngrok` now requires an account; a
[cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
quick tunnel doesn't:

```bash
cloudflared tunnel --url http://localhost:8000
```

Register the printed `https://*.trycloudflare.com/webhook` URL in Meta's
Business app (WhatsApp product → Configuration → Webhook), subscribe to the
`messages` field, and message your test number from your phone.

### What needs your accounts (this session cannot create these)

| Env var | Where it comes from |
|---|---|
| `PHONE_NUMBER_ID`, `WABA_ID`, `ACCESS_TOKEN`, `APP_SECRET` | Meta for Developers → Business app → WhatsApp product |
| `VERIFY_TOKEN` | Any random string you pick, entered in both `.env` and Meta's webhook config |
| `GEMINI_API_KEY` | Google AI Studio |
| `MONGODB_URI` | MongoDB Atlas free cluster connection string |
| `STAFF_PHONE` | A WhatsApp number to receive handoff alerts |
| `ADMIN_TOKEN` | Any random string — protects the `/admin/*` endpoints |

## Going live (not done yet, on purpose)

This deploys the same way as every other app on the standing production
box, per `~/.claude/NEW-SERVER-RUNBOOK.md` — `git push origin main` to a
private repo, not the Railway/Render suggestion from the original spec.
`.github/workflows/deploy.yml` is written but inert:

1. Fill in the `.env` heredoc in the workflow with real values.
2. Paste the server's private key into the `SSH_KEY` block (runbook §6 Step
   3 — this step needs a human, always).
3. Re-verify port 8004 is actually free on the box with `ss -ltnp` before
   trusting it.
4. Add the DNS A record for `aiagentconvo.powersmy.biz`.
5. Push, watch the run, then point Meta's webhook at the production URL.

The deploy runs **two** systemd units from one workflow: `aiagentconvo`
(the FastAPI web service, behind Caddy) and `aiagentconvo-worker` (the
queue consumer, not HTTP-facing). Redis runs as a native `apt` package on
the same box — the box currently hosts no stateful services, and this app's
Redis usage is small enough that a managed service would be pure overhead.

## Interview prep — things to be able to explain

- Why the webhook returns 200 before doing any real work.
- Why dedupe keys on the WhatsApp message id, not anything the bot itself generates.
- Why booking goes through a button tap instead of the model just calling the tool from free text.
- How the atomic slot update prevents double-booking without a lock table.
- What happens when a tool raises inside the agent loop (`_dispatch_tool` catches it and feeds the model a `{"error": ...}` function response, so the model can react instead of the webhook 500ing).
- How handoff turns off the bot and how `/admin/release/{phone}` turns it back on.
- Why language detection is cached instead of run on every message, and why Hinglish and Telugu each need their own script rule.
- What a booking conversation costs on Gemini, and where that number is measured (`services/costs.py`, backed by every response's real `usage_metadata` — not estimated).
