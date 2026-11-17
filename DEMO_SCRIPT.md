# Demo script — 5 minutes

**Before you start:** `python -m streamlit run app.py`, sidebar shows
"🌐 Gemini + Google Search configured", browser at 100 % zoom, **Run history**
already has a couple of runs in it so the dashboard isn't empty.

**The five-minute path is 0 → 1 → 1b → 1c → 2 → 4**, which comes to about 4:50.
Step 3 (ambiguous identity) is there if you are ahead of time or they ask what
happens when the person can't be pinned down.

Decide beforehand which live prospect you'll type in step 1 — a real person in a
finance-operations or AP role at a company with an open AP job posting. Try it
once the hour before. If live research is risky on the day, run **Fixture A**
instead and say out loud that it is a fixture.

---

## 0 · Frame it — 30 s

> "An SDR with 200 prospects can't spend 20 minutes on each, so they send
> templates. This takes a name and a company, does the research, **scores every
> reason it found out of 10**, drafts from the strongest one, and hands the rep a
> draft to review — with the option to overrule the ranking. It never sends
> anything.
>
> Everything is judged against this one sentence —" *(point at the sidebar)*
> "— we sell invoice-to-PO matching with discrepancy routing. That's the whole
> product description the app is allowed to know."

---

## 1 · Happy path, live — 1 min 30 s

Type the prospect name and company → **Run research**.

While the stages tick over (Identity → Research → Signal selection → Draft):

> "It's confirming identity first, before spending anything on research. Then
> it searches company pages, job postings, announcements and interviews."

When it lands, walk the screen **top to bottom**:

- **Identity** — expand *Identity confirmed — how we know*: "it checked who this person is before spending anything on research."
- **Selected signal** (left column) — the score first: "**9 of 10**, ranked #1,
  recommended by the app." Then read the claim aloud, then the line under it:
  publisher, date, source link, text status. "*Verified source text* means the
  app fetched that page and matched the sentence word for word, so it's allowed
  in quotation marks. *Source-backed paraphrase* means a source backs the claim
  but we didn't match exact wording — so it can't be quoted." Click the source
  link.
  - **Why it ranked first** — read it: it beat the runner-up 9 to 7, mainly on
    product relevance, 3 against 1. "That sentence is generated from the numbers,
    not written by the model."
  - The four component scores: "Product relevance out of 3, prospect relevance
    out of 3, evidence quality out of 2, timeliness out of 2. The model gives the
    integers and a reason for each; the app validates them, totals them and does
    the sorting. The total scores the outreach angle — it is **not** a
    probability that she buys." Open **Why these scores** on one of them.
  - **Ranked signals** — "two eligible, one context only. The funding round
    scores 5 and is fenced off: it has no connection to invoice matching, so it
    cannot produce a draft at all."
- **Draft** (right column) — "The evidence stays on screen while you edit, so you
  can check the claim without leaving the page."
  > "It references the fact and ends with one question. It does *not* say they
  > have a backlog or are losing money — a job posting can't establish that."

---

## 1b · Overrule the ranking — 45 s

On signal **#2** (7 of 10, her own interview) click **Use this signal**.

> "The rep knows things the app doesn't. Maybe she'd rather open on what Priya
> said herself than on a job ad."

The draft is rewritten from that finding's evidence. Point at three things:

- The header now reads **Ranked #2 · Your choice — not the app's pick**, and the
  line beneath still says the app recommended #1. "The recommendation and the
  human's decision are kept apart, and both are saved."
- The draft on the right says **Written from signal #2**, and it quotes nothing —
  that finding is paraphrase, not verified source text.
- The status went back to *Awaiting review*. "A new draft hasn't been approved."

> "No search ran. It reused the research and the scores already on the run — the
> only call was the drafting one. Switching signals can't spend on search, and it
> can't create a second run."

If you had typed in the body first, it asks before replacing your edits —
replace, keep, or save them first.

---

## 1c · Approve — 20 s

Edit a word in the body → **Approve draft**. The editor locks and shows
*Review saved: approved* with a timestamp, and the **Use this signal** buttons
disappear.

> "Approving saves the reviewed version, the decision, and which signal it was
> written from. A finalised run is read-only — nothing re-runs research, and
> nothing creates a second run."

---

## 2 · Edge case — weak signal — 1 min

Back to **Research prospect** → **Fixture C · Daniel Okafor, Lumenbridge
Studios** → *Replay fixture*.

> "This is a fixture — no search runs, and it's labelled as a fixture
> everywhere, including in history. It rehearses the decision logic."

> "No two columns here — there's no draft to show. Instead it shows everything it
> scored. Identity is confirmed, the findings are verified, and look at the top
> one: **7 of 10**. He gave the talk himself and the sourcing is good. But he's VP
> Engineering at a games studio and the talk was about rendering pipelines, so
> product relevance is **0 of 3** — and that makes it *context only*, whatever the
> total says. Zero eligible signals, so the app refuses to draft. A high score
> cannot buy a product connection the evidence doesn't show."

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

> "One row per run: prospect and role, company, the signal it ended on written
> out in full **with its score**, status, date, and whether it was live or a
> fixture. The row from the run we just approved says *7 of 10 · reviewer's
> choice* — you can see at a glance that a human overruled the ranking."

Click the prospect name from step 1 — it reopens in place with the same signal,
the same scores, the reviewed draft and the approval, read-only.

> "Reopening makes no model call. All of that came out of the database."

> "This survives a browser reload, because it's in Postgres rather than session
> state."

---

## 5 · Close — 15 s

> "Four outcomes, not one: a draft to review, needs clarification, insufficient
> evidence, and research incomplete when the provider fails — that last one is
> deliberately *not* the same as finding nothing. Every reason to write is scored
> on the same rubric, the arithmetic and the gates are in Python rather than in
> the model, the human can overrule the ranking without spending another search,
> and nothing sends."

---

### If something goes wrong live

| Problem | Say this, then |
| --- | --- |
| Search slow / hangs | "Live web research — this is the real latency." Give it ~45 s, then switch to Fixture A. |
| `Research incomplete` appears | "That's the provider-failure path, and this is what it looks like." Click **Retry this run**. |
| Prospect comes back ambiguous | Use it — it's edge case B happening for real. Supply the profile URL and continue. |
| Nothing is found | "That's *Insufficient evidence*, and it's the correct answer." Then run Fixture A for the happy path. |
| Only one eligible signal live | Say so — the rationale sentence switches to "it is the only finding that qualifies". Show the switch on Fixture A instead. |
| Scoring comes back malformed | "That's the retry path: it retries once, then records *Research incomplete* rather than guessing a score." |
