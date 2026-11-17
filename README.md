# Personalised outreach — from prospect to draft

**ASA Case Study · PS-3 (GTM)**

A salesperson picks **one product**, then types a prospect's name and company.
The app researches public information with Gemini + Google Search, confirms it
has the right person, collects up to three credible findings, scores each of
them against the chosen product, drafts a short first-contact email from the
strongest one, and stops for human review. **No email is ever sent.**

### The product catalogue

Three fictional offerings, in `outreach/config.py`. The salesperson chooses one
per run, and that choice drives the research question, the scoring, the draft
and the history row. The capability lists are the complete and only claims the
app may make about each one.

| Product | Sold to | What it does |
| --- | --- | --- |
| **Expense receipt tracking** (default) | finance teams | Collect missing employee expense receipts, send reminders, track outstanding receipts |
| **Vendor onboarding** | procurement teams | Collect supplier documents, flag missing information, track onboarding approval |
| **Invoice matching** | accounts payable teams | Compare supplier invoices with purchase orders, route quantity or price discrepancies for review |

These are examples written for the assignment. They are not attributed to any
real company.

**The same finding can be a strong reason to write about one product and mere
background for another.** "The finance team follows up with employees about
missing expense receipts" is a direct hit for receipt tracking and says nothing
about invoice-to-PO matching — so for invoice matching it is shown, scored, and
refused as a basis for a draft.

**Changing product starts a new run.** It changes what we search for and how
every finding is scored, so a run keeps the product it was created with —
through retries, clarification, switching signals and reopening from history.

---

## 1 · Local setup

Requires Python 3.10+.

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

### Secrets

Two options — Streamlit secrets (also what Community Cloud uses) or a `.env`
file. Copy the example and fill it in:

```bash
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
```

| Key | Required | What it is |
| --- | --- | --- |
| `GOOGLE_API_KEY` | For live research | A Google AI Studio key with the Gemini API enabled: <https://aistudio.google.com/apikey> |
| `DATABASE_URL`   | Optional | Supabase Postgres URI for hosted history. Omit it and history goes to a local SQLite file. |

Both files are git-ignored. Without `GOOGLE_API_KEY` the app still starts and
the fixture scenarios still run; the new-prospect form refuses with a clear
message rather than failing mid-run.

### Launch

```bash
python -m streamlit run app.py
```

Opens on <http://localhost:8501>.

### Tests

Offline — no network, no API key:

```bash
python -m pytest tests -q
```

---

## 2 · The workflow

| Stage | What happens | Where |
| --- | --- | --- |
| 1 · Identity | One grounded search for this person at this company; a judging call decides `confirmed` / `ambiguous` / `not_found`. | `outreach/pipeline.py: stage_identity` |
| 2 · Research | Grounded search over company pages, job postings, announcements, interviews. Up to three findings extracted, each tied to a cited URL, then **verified**. | `stage_research` |
| 3 · Signal | Every verified finding is scored individually against the run's product on a fixed 10-point rubric, in **one** model call, then ranked, tie-broken and gated in Python. | `stage_score`, `rank_scores` |
| 4 · Draft | A subject and short body built from the top-ranked eligible signal only. | `stage_draft` |
| 5 · Human review | Edit, approve, reject — or switch to another eligible signal, which rewrites the draft from that evidence without repeating any research. | `app.py`, `pipeline.redraft` |

### Run statuses — these are different outcomes, not one failure bucket

| Status | Meaning |
| --- | --- |
| `Needs clarification` | Several people fit the name, or sources disagree about the current employer. Paused **before** research spend; the user supplies a profile link or a correction and continues. |
| `Insufficient evidence` | Research worked, but nothing credible connects this prospect to our offer. The app refuses to invent a reason to write, and records why. |
| `Research incomplete` | The search provider failed or is not configured. We do **not** know what the evidence says. Offers retry. |
| `Awaiting review` → `Approved` / `Rejected` | A draft exists and a human has it. |

### Scoring a signal — the 10-point rubric

Each candidate finding is scored on its own. The model returns four integers and
a short reason for each, keyed by the finding's stable `finding_id`; Python
validates, totals, sorts and decides eligibility.

| Component | Range | 0 means | top of range means |
| --- | --- | --- | --- |
| Product relevance | 0–3 | no demonstrated connection to a listed capability | the source explicitly describes a task this product handles |
| Prospect relevance | 0–3 | no demonstrated connection to the person's work | the person owns or publicly discussed this specific initiative |
| Evidence quality | 0–2 | unsupported or contradicted | a direct source — the company's own posting, or the person's own words |
| Timeliness | 0–2 | stale or undated | demonstrably current, such as an open role |

**The total scores the strength of an outreach angle. It is not a probability of
a sale**, and it is shown with that caveat everywhere it appears.

What Python decides, not the model:

- **Validation.** A missing, duplicate or unknown `finding_id`, a missing
  component, a non-integer or an out-of-range value is rejected outright. There
  is no "repair the output" path and no silent fallback to the first finding.
  Invalid output is retried **once**; a second failure saves `Research
  incomplete` with a retry action, because an unscored run is a provider
  problem, not a verdict on the prospect.
- **Eligibility, applied before any winner is chosen:**

  | Condition | Outcome |
  | --- | --- |
  | Failed source verification | **Excluded** from ranking and drafting. A model score can never promote it. |
  | Evidence quality 0 | **Excluded** — unsupported or contradicted. |
  | Product relevance **below 2**, or prospect relevance 0 | **Background only** — shown with its score, cannot generate a draft. |
  | Same event as a higher-scoring finding | **Excluded** as a duplicate, so one announcement cannot occupy two ranks. |
  | No eligible signal at all | `Insufficient evidence`, explaining the gap in terms of the chosen product. |

  The minimum product relevance of **2** is deliberate, and stricter than the
  earlier threshold of 1. A score of 1 means "same broad business area only" —
  a finance job title, a payables team, a procurement function. That is not a
  reason to write to someone about a specific product, so it is background.

- **A claimed connection has to be named.** Product relevance of 2 or 3 is only
  accepted when the model also returns one of *this* product's listed
  capabilities, copied exactly, plus a reason. A capability we do not sell, or
  a bare score with no reason, is rejected as malformed — the model cannot
  assert a product fit without saying which capability it means.

- **Order.** Usable signals by total descending; ties broken on product
  relevance, then prospect relevance, then evidence quality, then timeliness,
  then the original research order. Background-only and excluded findings sit
  below every usable one **however high their raw total** — the *No relevant
  finding* sample's best finding scores 7 of 10 and still produces no draft.

### Switching signal

The first draft uses the top-ranked eligible signal. **Use this signal** on any
other eligible finding rewrites the draft from that finding's evidence:

- the saved research and scores are reused — **no new web search, no re-scoring**,
  no second run;
- unsaved edits are confirmed first (replace them, keep them, or save them and
  then switch), and the held text is restored on every path that does not switch;
- the run returns to `Awaiting review` and needs a fresh approval;
- if regeneration fails, the previous draft **and** the signal it was written
  from are both restored, so the evidence on screen always matches the email;
- the app's own recommendation stays visible and labelled, so a reviewer can see
  that #1 was recommended while reviewing #2;
- an approved or rejected run is read-only — no switching, the same rule as the
  draft editor.

### How claims are kept honest

Three kinds of text are tracked separately, and only one of them may appear in
quotation marks:

| Provenance | Shown as | Rule |
| --- | --- | --- |
| `source_text` | A quotation | The app fetched the source page and matched the sentence **verbatim**. |
| `search_summary` | Paraphrase | A source backs the claim (page text or a cited grounding segment), but exact wording was not matched. |
| `model_generated` | Nothing | No source backs it. **Excluded** from selection and from the draft. |

Additional guards:

- A finding whose URL was **not** cited by the search is dropped outright
  (`pipeline.py`, the `allowed_urls` check) — the model cannot introduce a URL.
- A quote that cannot be matched on the page is deleted, not shown unverified.
- After drafting, any remaining quotation marks in the body are stripped unless
  the quoted span is inside the verified quote (`_strip_unverified_quotes`).
- An unresolved identity stops the run before any research spend, and a finding
  scored 0 for evidence quality is excluded from ranking and from drafting. A
  score is a review aid, never a buying probability: 8 of 10 with unsupported
  evidence produces no draft, and 7 of 10 with no connection to the chosen
  product is background only.
- Identity confirmation is deliberately **product-blind**, and so is finding
  extraction: what we sell steers where the search looks, never what a source
  is recorded as saying. Only the scoring step judges a finding against the
  product.
- The draft may note a fact and ask a question about it. It may not assert that
  the company has a backlog, loses money, or wants software — that rule is in
  the drafting prompt (`outreach/prompts.py`).

---

## 3 · Sample scenarios

Five scenarios in `outreach/fixtures.py`, shown in the interface as **"Try an
example"** and labelled *Sample data · no live search*. They run **no search and
no model call**, are stored with `mode = "fixture"`, and carry their product
like any other run. The people, companies and URLs are fictional. **A sample run
is never evidence that live integration works.**

Each scenario declares only its findings and the raw scores a model might
return; eligibility, ranking, the checks and the "why it came first" sentence
are computed by the real pipeline, so a sample cannot display a verdict the live
code would not reach.

| Scenario | Product | What it shows | Ends at |
| --- | --- | --- | --- |
| **Strong match** | Expense receipt tracking | Hannah Weiss, Meridian Outfitters. An open expense role naming receipt chasing at **9/10**, her own interview at **8/10**, a new distribution centre at **5/10, background only**. Switching to the runner-up uses a stored draft, so it works with no API key. | `Awaiting review` |
| **Strong match** | Invoice matching | Priya Raghavan, Northwind Logistics. A verified AP posting at **9/10**, her interview at **8/10**, a funding round at **5/10, background only**. | `Awaiting review` |
| **Two people with the same name** | Expense receipt tracking | Michael Chen, Veridian Health. The run pauses before any research spend. | `Needs clarification` |
| **No relevant finding** | Invoice matching | Daniel Okafor, Lumenbridge Studios. The best finding scores **7/10** and is still background only. | `Insufficient evidence` |
| **Research interrupted** | Vendor onboarding | Alina Moreau, Castellan Foods. A retryable provider failure, not a conclusion. | `Research incomplete` |

The submitted app also accepts a new prospect and runs the real research path.

---

## 4 · Persistence

One table, `runs`: the columns the history view filters on, plus the whole run
as JSON so nothing is lost and no migration is needed.

```
runs(run_id PK, created_at, updated_at, prospect_name, company, status, mode, payload)
```

- **`DATABASE_URL` set** → Supabase Postgres (`JSONB` payload, `ON CONFLICT` upsert).
- **unset** → SQLite at `outreach_runs.db`.

Saves are upserts keyed on `run_id`, so editing or approving a draft updates the
same row. Approving, saving edits, rejecting or switching signal **never**
triggers another search and never creates a second run.

The payload carries a **snapshot of the product** — its id, name, who it is
sold to, its description and its capability list — so reopening a run shows the
offering it was actually researched for, even if the catalogue has since moved
on. A payload with no product predates product selection; those runs were all
invoice-matching runs and are shown as *Invoice matching (before product
choice)* rather than being relabelled or rescored.

The payload also carries the component scores and their reasons, the ranking, the
recommended `finding_id`, the reviewer's active `finding_id` and the draft's own
`finding_id`. Reopening a run from history therefore restores exactly what the
reviewer saw, with **no model call**. A run saved before ranking existed still
opens with its original evidence and draft, labelled "no score recorded" — no
scores are invented for it.

### Supabase setup

1. Create a project at <https://supabase.com>.
2. **Project Settings → Database → Connection string → URI**, and use the
   connection pooler (port `6543`) — Community Cloud needs the pooler.
3. Put that URI in `DATABASE_URL`. The table is created on first run.

---

## 5 · Deploying to Streamlit Community Cloud

1. Push this folder to a GitHub repository. Check that `.env`,
   `.streamlit/secrets.toml` and `outreach_runs.db` are **not** in the commit —
   `.gitignore` covers all three.
2. <https://share.streamlit.io> → **New app** → pick the repo/branch, main file
   `app.py`.
3. **Advanced settings → Secrets**: paste the contents of
   `.streamlit/secrets.toml.example` with real values. Set `DATABASE_URL` there
   too — Community Cloud's filesystem is ephemeral, so SQLite history would be
   lost on every restart.
4. Deploy. First boot installs `requirements.txt`.

---

## 6 · What was reused from the Agentic-Harness repo

| Taken from | Used for | Changed how |
| --- | --- | --- |
| `shared/research_agent.py` | How a grounded search is invoked. | That helper returned summary text only. `gemini_client.grounded_search` returns text **and** its sources, so claims can be attributed. ADK's `Runner`/`Agent` wrapper was dropped for a direct `google-genai` call — fewer dependencies and no event loop to manage inside Streamlit. |
| `shared/deep_search_agent.py` → `collect_research_sources_callback` | The claim → source-URL mapping. | Rewritten as `gemini_client.collect_sources_from_response` to read a `google-genai` response instead of ADK session events. The Apache-2.0 notice is kept in that file. |
| `main.py` → `run_approval_loop` | The human-in-the-loop review cycle (approve / modify / reject). | Re-implemented as Streamlit controls — edit in place, Approve, Save edits, Reject — with the decision and the reviewed version persisted. |

Deliberately **not** carried over: the specification-writing and coding agents,
the testing agent, the PDF vector database (`turbovec`, `sentence-transformers`,
`torch`, `pdfplumber`, …) and their dependencies. None of them serve this
workflow. `requirements.txt` is four lines.

---

## 7 · Interface

Light background, one accent colour (`#2563EB`) reserved for the primary action,
and every status carries a **text label**, never colour alone. The theme lives in
`.streamlit/config.toml`; the layout CSS is at the top of `app.py`.

It is written for a salesperson who knows their customers and has never heard
the words *fixture*, *grounding* or *eligibility*. Internal status values, stage
names and score keys are unchanged — storage, tests and the pipeline all still
use them — but nothing on screen does:

| Internally | On screen |
| --- | --- |
| fixture | Sample scenario · *Sample data · no live search* |
| human review (HITL) | Your review |
| `eligible` | Can use in draft |
| `context_only` | Background only, with the reason |
| `Insufficient evidence` | No strong signal found, with what was missing |
| `Research incomplete` | Research interrupted, with a *Try again* button |
| `Awaiting review` | Needs your review |
| product / prospect relevance, evidence quality, timeliness | Product fit · Relevant to their role · Source quality · Timing |

Model names, database details, run ids and raw provider errors live in one
**Technical details** expander at the foot of every result.

**Research a prospect** is the main screen. The product selector, prospect name
and company sit together, with the chosen product's description directly
beneath the selector; role, website and profile link are grouped under
*Additional details*; the primary button is **Research prospect**. The sample
scenarios sit to the side under *Try an example*, each labelled with its
product. When live research is unavailable the screen says exactly that — "Live
research is unavailable. You can still try an example." — and the cause and
setup steps go in an expander.

As a run executes, the stage strip reads **Confirming identity · Finding
sources · Comparing signals · Preparing draft · Your review**, with the real
stage message underneath.

A finished run answers four questions in reading order:

1. *Who did we research, and for what?* — a compact header: prospect, role,
   company, the product, live or sample, and the review status.
2. *What did we find?* — the left column leads with the finding itself as the
   largest text on the page, then publisher · date · clickable source · whether
   it can be quoted, then the verified excerpt when there is one. A paraphrase
   is labelled *Summary of the source*.
3. *Why does it matter for this product?* — one plain sentence built from the
   scores the model gave and the capability it named, with **Signal strength ·
   9/10** beside it and the four parts of the score as chips. The detail sits
   under *How this was scored*. Below that, **Other signals we found** ranks
   everything, marks what can and cannot be used, keeps *Our pick* and *Your
   pick* distinguishable, and puts **Use this signal** on each usable
   alternative.
4. *What can I do next?* — the right column holds the editable subject and
   email with **Approve draft**, **Save edits** and **Reject draft** beneath it.
   The evidence stays on screen while you edit; after an action the editor locks
   and says what was saved and when.

The screens that produce no draft each say what happened and what to do next:

- **Confirm who you mean** — the possible matches with their sources, a line
  like "We found 3 possible matches for this name. Add a profile link to confirm
  the right person", then a field for a link or a correction.
- **No strong signal found** — everything that was checked, each with its score
  and the reason it is background only, plus the suggestion to try the prospect
  again with a different product.
- **Research interrupted** — kept firmly distinct from the above: nothing was
  concluded, and there is a **Try again** button. The raw error is in Technical
  details.

**Past runs** is one row per run: prospect (and role), company, **Selling**, what
we used (the signal as a full sentence with its score, and "reviewer's choice"
when it is not our pick), status with live/sample beneath, and the date.
Selecting a row reopens the saved result in place — same product, same evidence,
same reviewed email — with no model call.

On screens under 900px the columns stack: what we found, then the other signals,
then the email, with the review controls full width.

## 8 · Layout

```
app.py                       Streamlit UI — two views, live stages, review controls
outreach/
  config.py                  Product catalogue, models, secrets/env loading
  gemini_client.py           Grounded search + source collection + JSON calls
  prompts.py                 Every prompt, in one readable place
  pipeline.py                The four stages, scoring/ranking, and redraft
  verify.py                  Page fetch, quote matching, provenance decisions
  schema.py                  Run / Product / Finding / Score / Source / Check / Draft + statuses
  store.py                   SQLite and Postgres persistence
  fixtures.py                Five sample scenarios, one per outcome
tests/test_offline.py        53 offline checks (no network, no API key)
.streamlit/config.toml       Light theme and accent colour
```

## 9 · Known limits

- Verification fetches the source page with a plain HTTP request. Sites that
  need JavaScript or block bots (LinkedIn among them) return no text, so their
  claims fall back to grounding-segment corroboration and are never quotable.
- Research is capped at a few grounded calls per run to stay demo-fast; depth is
  traded for latency on purpose.
- Sample-scenario data is fictional and its URLs do not resolve.
- The three products are examples written for this assignment, with no real
  company behind them.
