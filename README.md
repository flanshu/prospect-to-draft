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
| 3 · Signal | The verified findings are compared against the seller profile. One is selected, with a one-sentence reason and four reviewable checks. | `stage_signal` |
| 4 · Draft | A subject and short body built from the selected evidence only. | `stage_draft` |
| 5 · Human review | Edit, approve or reject in the UI. The workflow ends here. | `app.py` |

### Run statuses — these are different outcomes, not one failure bucket

| Status | Meaning |
| --- | --- |
| `Needs clarification` | Several people fit the name, or sources disagree about the current employer. Paused **before** research spend; the user supplies a profile link or a correction and continues. |
| `Insufficient evidence` | Research worked, but nothing credible connects this prospect to our offer. The app refuses to invent a reason to write, and records why. |
| `Research incomplete` | The search provider failed or is not configured. We do **not** know what the evidence says. Offers retry. |
| `Awaiting review` → `Approved` / `Rejected` | A draft exists and a human has it. |

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
- A failed **Evidence** check, or an unresolved identity, stops the run before
  drafting. "3 of 4 checks met" is a review aid, never a buying probability, and
  never overrides those gates.
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
| A | Happy path — Priya Raghavan, Northwind Logistics | `Awaiting review`, 4 of 4 checks |
| B | Ambiguous identity — Michael Chen, Veridian Health | `Needs clarification` |
| C | Weak signal — Daniel Okafor, Lumenbridge Studios | `Insufficient evidence`, 3 of 4 checks |
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
same row. Approving, saving edits or rejecting **never** triggers another search
and never creates a second run.

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
   the finding as a readable sentence, then publisher · date · clickable source ·
   text status, then the verified excerpt if there is one, then one sentence on
   why it matters to this prospect, then the four checks. Alternative findings
   sit in an expander below.
3. *Does the email use it accurately?* — the right column holds the editable
   subject and body with **Approve draft** / **Reject draft** directly beneath,
   and the evidence stays on screen while you edit. After a decision the editor
   locks and shows the saved review status.

Exception states replace the two columns with an actionable panel:

- **Needs clarification** — the possible matches, each with its source link, then
  a field for a profile URL or a correction, and a primary *Confirm and continue*.
- **Insufficient evidence** — what was checked, the closest finding, and the
  checks grid with the failed check highlighted, so it is clear why no draft was
  produced.
- **Research incomplete** — the provider error and a *Retry this run* button.

**Run history** is one row per run: prospect (and role), company, the selected
signal as a full sentence, status, date and live/fixture mode. Selecting a row
reopens the saved result in place, review controls included.

On screens under 900px the columns stack, signal above draft.

## 8 · Layout

```
app.py                       Streamlit UI — two views, live stages, review controls
outreach/
  config.py                  Seller profile, models, secrets/env loading
  gemini_client.py           Grounded search + source collection + JSON calls
  prompts.py                 Every prompt, in one readable place
  pipeline.py                The four stages and the orchestrator
  verify.py                  Page fetch, quote matching, provenance decisions
  schema.py                  Run / Finding / Source / Check / Draft + statuses
  store.py                   SQLite and Postgres persistence
  fixtures.py                Four rehearsal scenarios
tests/test_offline.py        19 offline checks (no network, no API key)
.streamlit/config.toml       Light theme and accent colour
```

## 9 · Known limits

- Verification fetches the source page with a plain HTTP request. Sites that
  need JavaScript or block bots (LinkedIn among them) return no text, so their
  claims fall back to grounding-segment corroboration and are never quotable.
- Research is capped at a few grounded calls per run to stay demo-fast; depth is
  traded for latency on purpose.
- Fixture data is fictional and the fixture URLs do not resolve.
