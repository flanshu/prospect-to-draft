# Handoff

**Built:** 16 November 2026 · ranked signals 17 November 2026 ·
**multi-product support and a plain-language interface, 17 November 2026**
PS-3 "Personalised outreach — from prospect to draft"
**Location:** `D:\OA\zamp` · entry point `app.py`

---

## What works

The whole workflow is built and running: **one product chosen per run**, a
prospect form, identity confirmation with a clarification pause, grounded web
research with per-claim attribution, verification of claims against source
pages, scoring of every candidate signal against that product on a fixed
10-point rubric with ranking in Python, email drafting from the strongest usable
signal, human review (edit / approve / reject / switch signal), and persisted
run history across two views.

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

---

## Multi-product support (added 17 November 2026)

**Files changed**

| File | What changed |
| --- | --- |
| `outreach/schema.py` | New `Product` dataclass (id, name, target users, description, capabilities, `legacy` flag) with exact capability matching; `Score.capability`; `Run.product`; `MIN_PRODUCT_RELEVANCE = 2`; a payload with no product rebuilds as the legacy invoice product. |
| `outreach/config.py` | The three-product catalogue, `DEFAULT_PRODUCT_ID`, `product()`, `default_product()`, `legacy_product()`, `product_choices()`. The old `SELLER_PROFILE` / `SELLER_CAPABILITIES` constants are gone. |
| `outreach/prompts.py` | `SELLER_BLOCK` replaced by `seller_block(product)`; the research search prompt now carries the product and its capabilities; the scoring rubric is the new product-relevance scale and requires a named capability; the draft prompt takes the product and the one capability to write about. Identity and extraction prompts are deliberately product-blind. |
| `outreach/pipeline.py` | `_parse_scores` takes the run's product and validates the named capability; `_apply_eligibility` uses the new threshold with product-aware wording; the `Insufficient evidence` reason names the product and suggests another; new `why_it_matters()`; research, scoring and drafting all read `run.product`. |
| `outreach/fixtures.py` | Five scenarios, each declaring its product. New **E** for the default product. **A** rescored under the new threshold (9 / 8 / 5). Eligibility, ranking, checks and the rationale are now computed by the real pipeline rather than hand-written. |
| `outreach/store.py` | New `_product_text()`; history rows carry the product, with pre-dropdown runs labelled. |
| `app.py` | Product selector driving the form and the sidebar; the whole interface rewritten in plain language (see below). |
| `tests/test_offline.py` | 39 → **53** checks. |
| `README.md`, `DEMO_SCRIPT.md` | Rewritten for one-product-per-run and the new labels. |

**How to run the demo**

`python -m streamlit run app.py`, then **Try an example → Strong match ·
Expense receipt tracking**. No API key is needed to pick a product, see the
scoring, switch signals, approve, or reopen from history.

**The product catalogue** lives in `outreach/config.py`: Expense receipt
tracking (the default), Vendor onboarding, Invoice matching. Each has a
capability list that is the complete set of claims the app may make about it.
They are examples written for the assignment and are attributed to no real
company.

**What the product changes.** Identity confirmation is product-blind — the only
question there is whether we have the right human. From then on the product
drives the research search prompt, the scoring call, the eligibility gates, the
draft and the history row. Finding *extraction* is also deliberately
product-blind, so what we sell steers where the search looks but never what a
source is recorded as saying.

**The threshold moved from 1 to 2, deliberately.** Product relevance 1 means
"same broad business area only" — a finance title, a payables team. That is not
a reason to write to someone about a specific product, so it is now background
only. The consequence is visible in the samples: fixture A's runner-up was
re-judged from 1 to 2 under the new scale ("a related workflow is described, but
the exact task is unclear") and totals 8 rather than 7.

**A claimed connection must be named.** Product relevance of 2 or 3 is accepted
only when the model also returns one of *that run's* product's capabilities,
copied exactly, with a reason. A capability we do not sell, or a bare score, is
rejected as malformed and takes the existing retry-once-then-`Research
incomplete` path. This is what makes the "Why this matters" sentence possible
without inventing anything: it is built from the model's own two reasons plus
the capability it named.

**The acceptance example** is a test, not a sample scenario:
`test_the_same_finding_is_usable_for_one_product_and_background_for_another`
takes the sentence *"The finance team follows up with employees about missing
expense receipts"* and scores it under both products. For receipt tracking it is
3/3 on product fit and usable; for invoice matching it is 1/3, totals 7, and
Python classifies it as background only with no draft. The demo narrates that
contrast rather than clicking it — adding a sixth sample for one talking point
seemed worse than one test that proves it.

**A run keeps its product.** Chosen once at creation and read from the run
thereafter, so retries, clarification, switching signals and reopening from
history all keep it — even when a different product is selected on the form.
Verified in the browser: the receipt-tracking sample ran with the form set to
Vendor onboarding and stayed on receipt tracking throughout.

**Old runs** have no product in their payload. They were all invoice-matching
runs, so they rebuild as Invoice matching with a `legacy` flag and are shown as
*Invoice matching (before product choice)*. Their stored scores, drafts and
review decisions are untouched and nothing is rescored. The flag survives a
re-save, so approving an old run does not relabel it.

## Interface, in plain language

The whole front end was rewritten for a salesperson who has never heard the
words *fixture*, *grounding* or *eligibility*. Internal status values, stage
names and score keys are unchanged — storage, tests and the pipeline still use
them — but nothing on screen does:

| Internally | On screen |
| --- | --- |
| fixture | Sample scenario · *Sample data · no live search* |
| human review | Your review |
| `eligible` | Can use in draft |
| `context_only` | Background only, with the reason |
| `Insufficient evidence` | No strong signal found |
| `Research incomplete` | Research interrupted, with *Try again* |
| `Awaiting review` | Needs your review |
| the four rubric components | Product fit · Relevant to their role · Source quality · Timing |
| stages | Confirming identity · Finding sources · Comparing signals · Preparing draft · Your review |

Model names, database details, run ids, product ids and raw provider errors all
moved into one **Technical details** expander at the foot of every result.

The new-run screen groups the product selector, name and company together with
the product's description under the selector; role, website and profile link are
under *Additional details*; the samples sit to the side under *Try an example*
with descriptive names (**Strong match**, **Two people with the same name**,
**No relevant finding**, **Research interrupted**). With no API key the screen
says "Live research is unavailable. You can still try an example", and the cause
and setup steps are in an expander.

A result leads with the finding as the largest text on the page, then its source
line, then **Why this matters for <product>**, then **Signal strength · 9/10**
and the four chips, with the detail under *How this was scored*. **Our pick** and
**Your pick** stay distinguishable. The email sits on the right with Approve /
Save edits / Reject beneath it and the evidence visible throughout.

## Interface (ranked-signals pass)

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

**Multi-product and the new interface, checked in the browser on 17 November:**

- New-run screen: the product selector, prospect name and company together, the
  chosen product's description beneath the selector, and *Additional details*
  collapsed. With no API key the screen reads "Live research is unavailable. You
  can still try an example" and **Research prospect** is disabled.
- Changing the selector to **Vendor onboarding** updated the description *and*
  the sidebar (name, description and all three capabilities) on the same
  interaction.
- **Strong match · Expense receipt tracking** replayed with the form still set
  to Vendor onboarding → the run stayed on **Expense receipt tracking**
  throughout, and the sidebar switched to "This run is selling". Signal #1 at
  **9/10** with *Why this matters for Expense receipt tracking*, #2 at **8/10**,
  the distribution centre at **5/10** marked *Background only* with its reason
  and no switch button. Other signals read "2 of 3 can be used in a draft".
- **Use this signal** on #2 → the email was rewritten from her interview (read
  the textarea value, not the label), the header read *Ranked #2 · Your pick*,
  the caption still said *Our pick was #1 … (9/10)*, and the product did not
  change.
- **Approve draft** → `Approved`, editor disabled, every **Use this signal**
  button gone, *Approved and saved* shown.
- **Past runs** → the new **Selling** column; the approved row read
  *8 of 10 · reviewer's choice*; runs saved earlier the same day, before this
  change, showed *Invoice matching (before product choice)*.
- **Two people with the same name** → *Confirm who you mean*, three candidates
  with sources, and the line "We found 3 possible matches for this name. Add a
  profile link to confirm the right person."
- **No relevant finding** → *No strong signal found*, all three findings marked
  *Background only*, the stop reason naming Invoice matching and suggesting
  another product.
- **Research interrupted** → the vendor-onboarding header, "Nothing was decided
  about this prospect", a **Try again** button, and the 503 moved out of the
  panel into Technical details.
- Narrow screen (375px) → stacks *What we found → Other signals → Your email*,
  zero horizontal overflow, and Approve / Save / Reject each 343×40 px (checked
  in the DOM, not by eye).

**The ranked-signal work was exercised in the browser earlier on 17 November:**

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

`python -m pytest tests -q` → **53 passed**, no network, no API key. They cover:
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

The 14 added for multi-product support cover both layers the brief asked to keep
apart. **Python, with mocked scores:** the catalogue's shape and default; a new
run carrying the default product; the acceptance example scoring 3/3 for receipt
tracking and 1/3 — background only, no draft — for invoice matching; product
relevance 1 being background rather than usable while a weaker total of 5 is the
recommendation; a claimed connection rejected when it names no capability, names
a capability the run's product does not have, or gives no reason, and accepted in
the catalogue's own wording; `why_it_matters` built only from the reasons and the
capability already scored, and saying nothing about the product when none was
named. **The calls themselves:** that the research search prompt, the scoring
prompt and the draft prompt each carry the product name and its capabilities,
that the identity prompt does not, that the named capability reaches the drafting
call, and that no other product's name leaks into any prompt. **Carrying it
through:** a payload with no product rebuilding as a flagged legacy invoice run
and keeping that flag across a re-save; switching signals leaving the product
untouched and logging it; retrying an interrupted run researching the original
product rather than the form default; every sample scenario declaring its
product with no code words in its name; the default product's sample scoring
9 / 8 / 5 with both usable signals naming a real capability; its stored
alternative email quoting nothing; and the whole demo flow for it — replay,
switch, approve, reload from SQLite — ending with the same product, signal and
email. One check greps the pipeline and the prompt templates for single-product
wording, so a product-specific sentence cannot creep back into shared code.

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
6. **A live redraft.** Switching signal was exercised with the sample's stored
   draft; the live path calls the model once through `stage_draft` and has not
   been run.
7. **Whether a real Gemini call returns a usable `capability` field.** Python
   requires one of the run's own capabilities, copied exactly, whenever product
   relevance is 2 or 3. The validation and both retry paths are tested with
   mocks, but no live call has produced that field. If the model paraphrases the
   capability instead of copying it, the run retries once and then becomes
   `Research interrupted` — correct behaviour, but how often it happens live is
   unknown, and it is the first thing to watch on your first real run.
8. **Whether live research actually finds different evidence per product.** The
   product reaches the search prompt (tested), but whether searching for receipt
   chasing versus invoice matching returns genuinely different sources for the
   same prospect has not been observed. Running one prospect twice, once per
   product, is the cheapest way to see it.
9. **Vendor onboarding end to end.** It exists in the catalogue and in the
   interrupted sample, but no run has ever scored or drafted for it, live or
   offline.
10. Supabase Postgres: `DATABASE_URL` is not set, so the Postgres branch of
    `store.py` has never connected. Only SQLite was exercised.
11. Streamlit Community Cloud deployment.

---

## Your next actions

1. **Get a Gemini key** — <https://aistudio.google.com/apikey> — and put it in
   `.streamlit/secrets.toml` (copy `.streamlit/secrets.toml.example`).
2. **Run one real prospect** and open the source link next to the email: does
   that page actually support the claim? This is the one check nobody else can
   do for you, and it is what the interviewer will do. While you are there, look
   at the four part-scores and ask whether you would have given the same
   integers, check that the capability named under *How this was scored* is one
   we actually sell, and switch to the runner-up once, to see a live redraft.
3. **Run the same prospect twice, once per product.** It is the fastest way to
   see whether the product really changes the research and the ranking, and it is
   the obvious thing an interviewer will ask you to do.
4. **Create the Supabase project**, set `DATABASE_URL` (pooler URI, port 6543),
   run once, and confirm history survives a restart.
5. **Deploy** — README §5. Keep `.env` and `secrets.toml` out of the commit;
   `.gitignore` already covers them.
6. **Rehearse** with `DEMO_SCRIPT.md`, picking your live prospect in advance and
   trying it an hour before.

## Things to know before you demo

- Sample-scenario URLs are fictional and will not resolve. The banner says so;
  say it out loud too.
- A sample run paused at *Confirm who you mean* switches to **live** research if
  you continue it — the app warns you and relabels the run.
- The three products are examples written for the assignment. If asked, say so
  plainly: they are not anyone's real product line, and the capability lists
  exist so the app has something it is forbidden to exceed.
- The strongest answer to "why one product per run?" is that it changes the
  research question, so mixing products would mean either searching for all of
  them or scoring findings against a yardstick they were not found for. Changing
  product therefore starts a new run.
- Research is capped at a few grounded calls per run, deliberately, for live
  latency. That is a defensible answer to "why isn't it deeper?".
- The scores come from the model; the arithmetic, the ordering and the gates do
  not. That is the line to hold if asked how much you trust the number. The
  capability requirement is the sharpest example: the model can say "this is a
  3", but only if it also names which of our capabilities it means, and Python
  checks that name against the run's own product.
- The product-relevance threshold of 2 is a judgment call, not a law. Be ready
  to say why: a score of 1 is "same broad business area", which is a description
  of the prospect's industry rather than a reason to write to them.
- If asked what you would build next: fetching that survives JS-rendered pages,
  a per-prospect research budget, calibrating the rubric against replies rather
  than asserting the weights, and a feedback loop from reply rates back into
  signal scoring.
