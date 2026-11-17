# Handoff

**Built:** 16 November 2026 · **ranked signals added 17 November 2026**
PS-3 "Personalised outreach — from prospect to draft"
**Location:** `D:\OA\zamp` · entry point `app.py`

---

## What works

The whole workflow is built and running: a prospect form, identity confirmation
with a clarification pause, grounded web research with per-claim attribution,
verification of claims against source pages, **scoring of every candidate signal
on a fixed 10-point rubric and ranking in Python**, email drafting from the top
eligible signal, human review (edit / approve / reject / **switch signal**), and
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

## Ranked signals (added 17 November 2026)

**Files changed:** `outreach/schema.py` (new `Score` dataclass, `finding_id` on
`Finding`, `finding_id` on `Draft`, and `scores` / `ranking` / `recommended_id` /
`active_id` on `Run`, with the helpers to read them), `outreach/prompts.py`
(`SIGNAL_SELECT` replaced by `SIGNAL_SCORE`, the rubric in full),
`outreach/pipeline.py` (`stage_signal` replaced by `stage_score` plus
`_parse_scores`, `_apply_eligibility`, `rank_scores`, `winner_rationale`,
`_duplicate_of`, and the new `redraft` entry point), `app.py` (ranked-signal
panel, component scores, the switch flow and its unsaved-edit confirmation),
`outreach/fixtures.py` (fixture A rebuilt with three scored findings and a stored
alternative draft; fixture C rescored), `outreach/store.py` (history row shows the
active signal's score), `tests/test_offline.py` (20 new checks),
`README.md`, `DEMO_SCRIPT.md`.

**How to run it:** unchanged — `python -m streamlit run app.py`, then replay
fixture A. No API key is needed to see the ranking or to switch signals.

**What the model decides, and what it does not.** The model returns four
integers and a short reason per finding, keyed by `finding_id`, in one call.
Python validates the ids, the fields and the ranges, totals the scores, applies
the tie-breaks, and decides eligibility. There is no fallback that silently picks
the first finding: invalid scoring output is retried once, and a second failure
saves `Research incomplete` with a retry button rather than inventing a ranking.

**The gates, in order.** Failed source verification excludes a finding from
ranking and drafting whatever the model scored it. Evidence quality 0 excludes
it. Product relevance 0 or prospect relevance 0 makes it *context only* — shown
with its score, unable to produce a draft. A second report of an event already
ranked is set aside as a duplicate. No eligible signal means `Insufficient
evidence`, listing what was checked. Fixture C is the demonstration: its best
finding scores **7 of 10** and still produces no draft.

**Switching signal** reuses the saved research and scores — no search, no
re-scoring, no second run. The app's recommendation stays visible beside the
reviewer's choice, the run returns to `Awaiting review` for a fresh approval, and
a failed regeneration restores both the previous draft and the signal it was
written from, so the evidence on screen always matches the email. Approved and
rejected runs are read-only.

**Old saved runs** open with their original evidence and draft and are labelled
*no score recorded*. Nothing is scored retrospectively.

## Interface

Rebuilt against the Common Room / Lavender / Clay references: light theme, one
accent colour, text labels on every status, prospect header over a compact
five-stage indicator, and a two-column result — on the left the signal under
review (score out of 10, rank, claim, source, verified excerpt, why it ranked
first, component scores) above the full ranked list with a switch button on each
eligible alternative; on the right the editable draft with Approve / Reject
directly beneath it, evidence visible throughout. Exception states replace the columns with an
actionable panel. History is one row per run including the selected signal, and
clicking a row reopens it. Under 900px the columns stack, signal above draft.

## Tested live (in a browser, against the running app)

Streamlit app started, loaded, and driven end to end. The ranked-signal work was
exercised in the browser on 17 November:

- Fixture A replayed — stages animated; signal #1 at **9 of 10** with its
  component scores and reasons, #2 at **7**, the funding round at **5** labelled
  *Context only* with no switch button.
- **Use this signal** on #2 → the draft was rewritten from her interview, the
  header read *Ranked #2 · Your choice — not the app's pick*, the app's #1
  recommendation stayed on screen, and the editor showed the new email (checked
  the textarea value, not just the label).
- Typed an unsaved edit, then clicked **Use this signal** → the confirmation
  appeared; **Keep my edits** preserved the typed text and did not switch;
  **Replace my edits** switched and produced the new draft.
- **Approve draft** on the switched run → `Approved`, editor locked, and every
  **Use this signal** button gone (finalised runs are read-only).
- **Run history after a full browser reload** → the row read *7 of 10 ·
  reviewer's choice*; reopening it restored signal #2, its scores, the app's #1
  recommendation and the approved draft, read-only.
- A run **actually saved yesterday**, before ranking existed, reopened with its
  original evidence, draft and old-style checks, labelled *no score recorded*.
- Fixture C replayed → `Insufficient evidence` with all three findings scored,
  the best at **7 of 10**, each marked *Context only*, and no draft.
- **Approve draft** clicked → status `Approved`, editor locked, decision
  timestamped and saved.
- Fixture B replayed → `Needs clarification`, three candidates listed, the
  clarification form shown with a profile-URL field.
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

`python -m pytest tests -q` → **39 passed**, no network, no API key. They cover:
verbatim quote matching and its rejection of altered/short quotes, exclusion of
unverifiable findings, redirect resolution and publisher inference, the
draft quote-stripping guardrail, the "failed Evidence check overrides a 3-of-4
tally" rule, SQLite upsert (no duplicate rows, edits persist, reload works), and
the full pipeline with the search and model layers mocked — happy path,
uncited-URL rejection, ambiguous-identity pause, provider failure, and missing
credentials.

The 20 added for ranked signals cover: ranking order and every documented
tie-break (including a full tie falling back to research order, and model order
not mattering); context-only findings sitting below eligible ones despite a
higher total; an unverified finding excluded whatever the model scores it;
evidence quality 0 excluded rather than merely ranked low; a high total with a
failed evidence gate producing no draft; duplicate reports of one event taking
one rank; malformed scoring output in seven shapes, the retry-then-succeed path,
and the retry-then-`Research incomplete` path; switching signal making no search
call and exactly one drafting call while leaving sources and scores untouched;
switching to a context-only or unknown id refused; a failed regeneration keeping
the previous draft and signal together; the fixture switch needing no model call;
the whole demo flow (switch → approve → reload from SQLite) as one run; and a
legacy run with its ranking fields stripped still opening and being labelled
rather than scored.

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
5. **Whether a real Gemini call returns valid rubric scores** — the shape is
   validated and the retry path is tested with mocks, but no live scoring call
   has been made. If the model is loose with the integers in practice, the retry
   fires and then the run becomes `Research incomplete`; that is the designed
   behaviour, but how often it happens live is unknown.
6. **A live redraft.** Switching signal was exercised with the fixture's stored
   draft; the live path calls the model once through `stage_draft` and has not
   been run.
7. Supabase Postgres: `DATABASE_URL` is not set, so the Postgres branch of
   `store.py` has never connected. Only SQLite was exercised.
8. Streamlit Community Cloud deployment.

---

## Your next actions

1. **Get a Gemini key** — <https://aistudio.google.com/apikey> — and put it in
   `.streamlit/secrets.toml` (copy `.streamlit/secrets.toml.example`).
2. **Run one real prospect** and open the source link next to the draft: does
   that page actually support the claim? This is the one check nobody else can
   do for you, and it is what the interviewer will do. While you are there, look
   at the component scores and ask whether you would have given the same four
   integers — and switch to the runner-up once, to see a live redraft.
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
- The scores come from the model; the arithmetic, the ordering and the gates do
  not. That is the line to hold if asked how much you trust the number.
- If asked what you would build next: fetching that survives JS-rendered pages,
  a per-prospect research budget, calibrating the rubric against replies rather
  than asserting the weights, and a feedback loop from reply rates back into
  signal scoring.
