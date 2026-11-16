# Handoff

**Built:** 16 November 2026 · PS-3 "Personalised outreach — from prospect to draft"
**Location:** `D:\OA\zamp` · entry point `app.py`

---

## What works

The whole workflow is built and running: a prospect form, identity confirmation
with a clarification pause, grounded web research with per-claim attribution,
verification of claims against source pages, selection of one signal with four
reviewable checks, email drafting, human review (edit / approve / reject), and
persisted run history across two views.

The original ZIP in this folder is untouched; nothing was extracted into the
project directory.

**Four distinct outcomes**, not one failure bucket — `Needs clarification`,
`Insufficient evidence`, `Research incomplete`, `Awaiting review` → `Approved` /
`Rejected`.

**Reuse from your repo:** the grounded-search invocation from
`shared/research_agent.py` (extended to return sources, not just summary text),
the claim → source-URL mapping from `collect_research_sources_callback` in
`shared/deep_search_agent.py` (ported to read a `google-genai` response, Apache
notice kept in `outreach/gemini_client.py`), and the approve/modify/reject cycle
from `run_approval_loop` in `main.py` (now Streamlit controls). The spec,
coding and testing agents, the PDF vector DB and their dependencies are gone —
`requirements.txt` is four lines.

---

## Interface

Rebuilt against the Common Room / Lavender / Clay references: light theme, one
accent colour, text labels on every status, prospect header over a compact
five-stage indicator, and a two-column result — selected signal (claim, source,
verified excerpt, why it matters, four checks, alternatives in an expander) on
the left, editable draft with Approve / Reject directly beneath it on the right,
evidence visible throughout. Exception states replace the columns with an
actionable panel. History is one row per run including the selected signal, and
clicking a row reopens it. Under 900px the columns stack, signal above draft.

## Tested live (in a browser, against the running app)

Streamlit app started, loaded, and driven end to end:

- Fixture A replayed — stages animated, 4 of 4 checks, signal column and draft
  column rendered side by side with the verified excerpt in place.
- **Approve draft** clicked → status `Approved`, editor locked, decision
  timestamped and saved.
- Fixture B replayed → `Needs clarification`, three candidates listed, the
  clarification form shown with a profile-URL field.
- Fixture C replayed → `Insufficient evidence` at 3 of 4 checks, with the stop
  reason displayed and **no draft produced**.
- Fixture D replayed → `Research incomplete` with the provider error and a
  **Retry** button.
- **Run history** → one row per run with prospect, role, company, the selected
  signal in full, status, date and mode; clicking a row reopened the approved run
  **after a full browser reload**, with evidence, reviewed draft and approval all
  restored from SQLite.
- Narrow screen (375px) → columns stack with the signal above the draft, and no
  horizontal overflow (checked in the DOM, not just by eye).
- Submitting the new-prospect form with no API key → a clear, actionable error
  instead of a mid-run crash.

## Tested with fixtures and offline tests only

`python -m pytest tests -q` → **19 passed**, no network, no API key. They cover:
verbatim quote matching and its rejection of altered/short quotes, exclusion of
unverifiable findings, redirect resolution and publisher inference, the
draft quote-stripping guardrail, the "failed Evidence check overrides a 3-of-4
tally" rule, SQLite upsert (no duplicate rows, edits persist, reload works), and
the full pipeline with the search and model layers mocked — happy path,
uncited-URL rejection, ambiguous-identity pause, provider failure, and missing
credentials.

## NOT verified — these need credentials

There is no `GOOGLE_API_KEY` on this machine, so **nothing below was executed
against the real provider**. No fixture result should be read as a live test.

1. A real Gemini call with the `google_search` tool: whether
   `grounding_chunks` / `grounding_supports` come back in the shape
   `collect_sources_from_response` expects on `google-genai` 1.75.
2. Whether live research finds enough for a real prospect in demo-acceptable time.
3. Live page fetching and verbatim quote matching against real pages — in
   particular, how often a real source page is fetchable (LinkedIn and many news
   sites will not be, which pushes findings to non-quotable paraphrase).
4. Draft quality and tone on real evidence.
5. Supabase Postgres: `DATABASE_URL` is not set, so the Postgres branch of
   `store.py` has never connected. Only SQLite was exercised.
6. Streamlit Community Cloud deployment.

---

## Your next actions

1. **Get a Gemini key** — <https://aistudio.google.com/apikey> — and put it in
   `.streamlit/secrets.toml` (copy `.streamlit/secrets.toml.example`).
2. **Run one real prospect** and open the source link next to the draft: does
   that page actually support the claim? This is the one check nobody else can
   do for you, and it is what the interviewer will do.
3. **Create the Supabase project**, set `DATABASE_URL` (pooler URI, port 6543),
   run once, and confirm history survives a restart.
4. **Deploy** — README §5. Keep `.env` and `secrets.toml` out of the commit;
   `.gitignore` already covers them.
5. **Rehearse** with `DEMO_SCRIPT.md`, picking your live prospect in advance and
   trying it an hour before.

## Things to know before you demo

- Fixture URLs are fictional and will not resolve. The fixture banner says so;
  say it out loud too.
- A fixture run paused at `Needs clarification` switches to **live** research if
  you continue it — the app warns you and relabels the run.
- Research is capped at a few grounded calls per run, deliberately, for live
  latency. That is a defensible answer to "why isn't it deeper?".
- If asked what you would build next: fetching that survives JS-rendered pages,
  a per-prospect research budget, and a feedback loop from reply rates back into
  signal selection.
