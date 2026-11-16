# Demo script — 5 minutes

**Before you start:** `python -m streamlit run app.py`, sidebar shows
"🌐 Gemini + Google Search configured", browser at 100 % zoom, **Run history**
already has a couple of runs in it so the dashboard isn't empty.

Decide beforehand which live prospect you'll type in step 2 — a real person in a
finance-operations or AP role at a company with an open AP job posting. Try it
once the hour before. If live research is risky on the day, run **Fixture A**
instead and say out loud that it is a fixture.

---

## 0 · Frame it — 30 s

> "An SDR with 200 prospects can't spend 20 minutes on each, so they send
> templates. This takes a name and a company, does the research, picks **one**
> real reason to make contact, and hands the rep a draft to review. It never
> sends anything.
>
> Everything is judged against this one sentence —" *(point at the sidebar)*
> "— we sell invoice-to-PO matching with discrepancy routing. That's the whole
> product description the app is allowed to know."

---

## 1 · Happy path, live — 2 min

Type the prospect name and company → **Run research**.

While the stages tick over (Identity → Research → Signal selection → Draft):

> "It's confirming identity first, before spending anything on research. Then
> it searches company pages, job postings, announcements and interviews."

When it lands, walk the screen **top to bottom**:

- **Identity** — expand *Identity confirmed — how we know*: "it checked who this person is before spending anything on research."
- **Selected signal** (left column) — read the claim aloud, then the line under
  it: publisher, date, source link, text status. "*Verified source text* means
  the app fetched that page and matched the sentence word for word, so it's
  allowed in quotation marks. *Source-backed paraphrase* means a source backs
  the claim but we didn't match exact wording — so it can't be quoted." Click
  the source link.
  - **Why it matters here** — one sentence tying the fact to her role and our offer.
  - **Checks** — "Four checks a human can argue with: Evidence, Role relevance,
    Product relevance, Timeliness. The tally underneath is a review aid, not a
    buying probability — and it can't override the first two gates."
  - Open **Other findings considered** — "these are the ones it passed over, each
    with its own source and text status."
- **Draft** (right column) — "The evidence stays on screen while you edit, so you
  can check the claim without leaving the page."
  > "It references the fact and ends with one question. It does *not* say they
  > have a backlog or are losing money — a job posting can't establish that."

Edit a word in the body → **Approve draft**. The editor locks and shows
*Review saved: approved* with a timestamp.

> "Approving saves the reviewed version and the decision. It doesn't re-run
> research and doesn't create a second run — the edit is the same row."

---

## 2 · Edge case — weak signal — 1 min 15 s

Back to **Research prospect** → **Fixture C · Daniel Okafor, Lumenbridge
Studios** → *Replay fixture*.

> "This is a fixture — no search runs, and it's labelled as a fixture
> everywhere, including in history. It rehearses the decision logic."

> "No two columns here — there's no draft to show. Instead it shows what it
> checked. Identity is confirmed. The findings are verified. But he's VP Engineering at
> a games studio and his talk was about rendering pipelines. **3 of 4 checks met
> — and the app still refuses to draft**, because Product relevance failed.
> There's no honest connection to invoice matching, and the alternative is
> inventing one. The status is *Insufficient evidence* and the reason is saved."

> "That's the decision I most wanted it to get right. A template generator would
> have written something here."

---

## 3 · Edge case — ambiguous identity (if time) — 45 s

**Fixture B · Michael Chen, Veridian Health** → *Replay fixture*.

> "Two people share the name, and the company's own pages disagree — a 2023
> press release names him, the current leadership page doesn't. So it stops at
> *Needs clarification*, before spending anything on research, and asks for a
> profile link or a correction. That's the SDR's judgment call, not the model's."

Paste a profile URL into the box to show the form (don't submit — it would start
a live run).

---

## 4 · History — 30 s

Sidebar → **Run history**.

> "One row per run: prospect and role, company, the signal it selected written
> out in full, status, date, and whether it was live or a fixture. You can read
> the whole list without opening anything."

Click the prospect name from step 1 — it reopens in place, evidence and reviewed
draft intact.

> "This survives a browser reload, because it's in Postgres rather than session
> state."

---

## 5 · Close — 15 s

> "Four outcomes, not one: a draft to review, needs clarification, insufficient
> evidence, and research incomplete when the provider fails — that last one is
> deliberately *not* the same as finding nothing. The human decides on every
> draft, and nothing sends."

---

### If something goes wrong live

| Problem | Say this, then |
| --- | --- |
| Search slow / hangs | "Live web research — this is the real latency." Give it ~45 s, then switch to Fixture A. |
| `Research incomplete` appears | "That's the provider-failure path, and this is what it looks like." Click **Retry this run**. |
| Prospect comes back ambiguous | Use it — it's edge case B happening for real. Supply the profile URL and continue. |
| Nothing is found | "That's *Insufficient evidence*, and it's the correct answer." Then run Fixture A for the happy path. |
