# Personalised outreach — from prospect to draft

**ASA Case Study · PS-3 (GTM)**

A salesperson types a prospect's name and company. The app researches public
information with Gemini + Google Search, confirms it has the right person,
collects up to three credible findings, picks **one** signal and explains why,
drafts a short first-contact email from that evidence, and stops for human
review. **No email is ever sent.**

The seller profile is fixed for the prototype and shown in the sidebar, so a
reviewer can always see the yardstick a finding was judged against:

> We sell software that helps accounts payable teams match supplier invoices to
> purchase orders and route discrepancies to a reviewer.

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
| 3 · Signal | Every verified finding is scored individually against a fixed 10-point rubric in **one** model call, then ranked, tie-broken and gated in Python. | `stage_score`, `rank_scores` |
| 4 · Draft | A subject and short body built from the top-ranked eligible signal only. | `stage_draft` |
| 5 · Human review | Edit, approve, reject — or switch to another eligible signal, which rewrites the draft from that evidence without repeating any research. | `app.py`, `pipeline.redraft` |

### Run statuses — these are different outcomes, not one failure bucket

| Status | Meaning |
| --- | --- |
| `Needs clarification` | Several people fit the name, or sources disagree about the current employer. Paused **before** research spend; the user supplies a profile link or a correction and continues. |
| `Insufficient evidence` | Research worked, but nothing credible connects this prospect to our offer. The app refuses to invent a reason to write, and records why. |
| `Research incomplete` | The search provider failed or is not configured. We do **not** know what the evidence says. Offers retry. |
| `Awaiting review` → `Approved` / `Rejected` | A draft exists and a human has it. |

### Ranked signals — the 10-point rubric

Each candidate finding is scored on its own. The model returns four integers and
a short reason for each, keyed by the finding's stable `finding_id`; Python
validates, totals, sorts and decides eligibility.

| Component | Range | 0 means | top of range means |
| --- | --- | --- | --- |
| Product relevance | 0–3 | no demonstrated connection to the offer | explicitly concerns invoice-to-PO matching or discrepancy review |
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
  | Product relevance 0, or prospect relevance 0 | **Context only** — shown with its score, cannot generate a draft. |
  | Same event as a higher-scoring finding | **Excluded** as a duplicate, so one announcement cannot occupy two ranks. |
  | No eligible signal at all | `Insufficient evidence`, listing the context-only findings and their scores. |

- **Order.** Eligible signals by total descending; ties broken on product
  relevance, then prospect relevance, then evidence quality, then timeliness,
  then the original research order. Context-only and excluded findings sit below
  every eligible one **however high their raw total** — fixture C's best finding
  scores 7 of 10 and still produces no draft.

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
  evidence produces no draft, and 7 of 10 with no product connection is context
  only.
- The draft may note a fact and ask a question about it. It may not assert that
  the company has a backlog, loses money, or wants software — that rule is in
  the drafting prompt (`outreach/prompts.py`).

---

## 3 · Rehearsal fixtures

Four labelled scenarios in `outreach/fixtures.py`. They run **no search and no
model call**, are stored with `mode = "fixture"`, and are labelled 🧪 in the run
view and in history. The people, companies and URLs are fictional. **A fixture
run is never evidence that live integration works.**

| Fixture | Scenario | Expected status |
| --- | --- | --- |
| A | Happy path — Priya Raghavan, Northwind Logistics. Three scored findings: the AP posting at **9/10**, her own interview at **7/10**, a funding round at **5/10, context only**. Switching to the runner-up uses a stored draft, so it works with no API key. | `Awaiting review` |
| B | Ambiguous identity — Michael Chen, Veridian Health | `Needs clarification` |
| C | Weak signal — Daniel Okafor, Lumenbridge Studios. The best finding scores **7/10** and is still context only. | `Insufficient evidence` |
| D | Provider failure — Alina Moreau, Castellan Foods | `Research incomplete` |

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

The payload carries the component scores and their reasons, the ranking, the
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

**Research prospect** answers three questions in reading order:

1. *What did we learn?* — prospect name, role and company sit above a compact
   five-stage indicator that updates as identity, research, selection and
   drafting actually execute.
2. *Where did we find it, and why does it matter?* — the left column leads with
   the signal under review: its score out of 10, its rank, and whether it is the
   app's recommendation or your own choice, then the claim, then publisher ·
   date · clickable source · text status, the verified excerpt if there is one,
   and one sentence on why it ranked first. Below it, **Ranked signals** lists
   every scored finding in order with its rank, total, eligibility label, source
   and component scores — reasons collapsed, open by default on the top signal —
   and a **Use this signal** button on each eligible alternative.
3. *Does the email use it accurately?* — the right column holds the editable
   subject and body with **Approve draft** / **Reject draft** directly beneath,
   and the evidence stays on screen while you edit. After a decision the editor
   locks and shows the saved review status.

Exception states replace the two columns with an actionable panel:

- **Needs clarification** — the possible matches, each with its source link, then
  a field for a profile URL or a correction, and a primary *Confirm and continue*.
- **Insufficient evidence** — the ranked list of everything that was checked,
  each with its score and the reason it is context only or excluded, so it is
  clear why no draft was produced.
- **Research incomplete** — the provider error and a *Retry this run* button.

**Run history** is one row per run: prospect (and role), company, the active
signal as a full sentence with its score (and "reviewer's choice" when it is not
the app's pick), status, date and live/fixture mode. Selecting a row
reopens the saved result in place, review controls included.

On screens under 900px the columns stack, signal above draft.

## 8 · Layout

```
app.py                       Streamlit UI — two views, live stages, review controls
outreach/
  config.py                  Seller profile, models, secrets/env loading
  gemini_client.py           Grounded search + source collection + JSON calls
  prompts.py                 Every prompt, in one readable place
  pipeline.py                The four stages, scoring/ranking, and redraft
  verify.py                  Page fetch, quote matching, provenance decisions
  schema.py                  Run / Finding / Score / Source / Check / Draft + statuses
  store.py                   SQLite and Postgres persistence
  fixtures.py                Four rehearsal scenarios
tests/test_offline.py        39 offline checks (no network, no API key)
.streamlit/config.toml       Light theme and accent colour
```

## 9 · Known limits

- Verification fetches the source page with a plain HTTP request. Sites that
  need JavaScript or block bots (LinkedIn among them) return no text, so their
  claims fall back to grounding-segment corroboration and are never quotable.
- Research is capped at a few grounded calls per run to stay demo-fast; depth is
  traded for latency on purpose.
- Fixture data is fictional and the fixture URLs do not resolve.
