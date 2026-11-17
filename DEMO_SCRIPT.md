# Demo script — 5 minutes

**Before you start:** `python -m streamlit run app.py`, sidebar shows
**Live research · ready**, browser at 100 % zoom, **Past runs** already has a
couple of runs in it so the screen isn't empty. Leave the product selector on
its default, **Expense receipt tracking**.

**The five-minute path is 0 → 1 → 1b → 1c → 2 → 4**, about 4:50. Step 3
(two people with the same name) is there if you are ahead of time or they ask
what happens when the person can't be pinned down.

Decide beforehand which live prospect you'll type in step 1 — a real person in a
finance-operations role at a company with an open expense or AP posting. Try it
once the hour before. If live research looks risky on the day, use **Strong
match · Expense receipt tracking** instead and say out loud that it is sample
data.

---

## 0 · Frame it — 30 s

> "An SDR with 200 prospects can't spend 20 minutes on each, so they send
> templates. This takes a product, a name and a company, does the research,
> **scores every reason it found out of 10 against that product**, drafts from
> the strongest one, and hands the rep an email to review. It never sends
> anything."

Point at the product selector:

> "Three products. The rep picks one per prospect, and that choice changes
> everything downstream — what we search for, how each finding is scored, which
> findings are allowed to produce an email at all. The capability list in the
> sidebar is the complete set of claims the app may make. It can't invent a
> fourth capability any more than it can invent a quote."

---

## 1 · One prospect, one product — 1 min 30 s

Leave the product on **Expense receipt tracking**, read the description under
the selector aloud, type the prospect name and company → **Research prospect**.

While the stages tick over — *Confirming identity · Finding sources · Comparing
signals · Preparing draft*:

> "Identity first, before spending anything on research. Then it searches with
> the product in hand: company process pages, policies, job postings describing
> that work, the person's own words."

When it lands, walk the screen **top to bottom**:

- **Header** — "prospect, company, what we're selling, whether it was live, and
  that it needs their review."
- **How we know it's the right person** — expand it. "It confirmed the human
  before spending on research."
- **What we found** (left column) — read the finding aloud; it's the biggest
  text on the page for a reason. Then the line under it: publisher, date, source
  link, and whether it can be quoted. "*Verified quote* means we opened that page
  and matched the sentence word for word, so the email may quote it. *Summary of
  the source* means a source backs the claim but we didn't match its wording —
  so the email won't quote it." Click the source link.
- **Why this matters for Expense receipt tracking** — read it. "That names the
  capability it connects to. The model has to say which one — a score of 2 or 3
  for product fit is rejected if it doesn't name a capability we actually sell."
- **Signal strength · 9/10** and the four chips — "Product fit, relevant to their
  role, source quality, timing. The model gives the integers and a reason for
  each; the app validates them, totals them, and does the sorting. The number
  describes the outreach angle — it is **not** a prediction that she buys." Open
  **How this was scored** on one.
- **Other signals we found · 2 of 3 can be used** — "the third one scores 5 and
  is fenced off as *Background only*: nothing in it describes a task this product
  handles, so it can't produce an email at all."

> "And this is the part worth noticing: that background-only finding isn't
> badly sourced. It's real, it's current, it's about the right company. It's just
> not about what we sell **this** time."

- **Your email** (right column) — "the evidence stays on screen while you edit,
  so you can check the claim without leaving the page."
  > "It names the fact, asks one question, and talks about exactly one
  > capability. It does *not* say they have a backlog or are losing money — a job
  > posting can't establish that."

---

## 1b · Overrule the ranking — 45 s

On signal **#2** (8 of 10, her own interview) click **Use this signal**.

> "The rep knows things the app doesn't. Maybe she'd rather open on what she said
> herself than on a job ad."

The email is rewritten from that finding. Point at three things:

- The header now reads **Ranked #2 · Your pick**, and the line beneath still
  says *Our pick was #1*. "Our recommendation and the human's decision are kept
  apart, and both are saved."
- The email says **Written from signal #2**, and it quotes nothing — that finding
  is a summary, not verified wording.
- The status went back to **Needs your review**.

> "No search ran, and the product didn't change. It reused the research and the
> scores already on the run — the only call was the one that wrote the email.
> Switching signals can't spend on search and can't start a second run."

If you had typed in the email first, it asks before replacing your changes —
replace, keep, or save them first.

---

## 1c · Approve — 20 s

Edit a word → **Approve draft**. The editor locks, shows **Approved and saved**
with a timestamp, and the **Use this signal** buttons disappear.

> "Approving saves the reviewed version, the decision, and which signal it was
> written from. A finished run is read-only."

---

## 2 · The same evidence, a different product — 1 min

Back to **Research a prospect** → **No relevant finding · Invoice matching** →
*Try this example*.

> "Sample data — nothing searched. Daniel Okafor, VP Engineering at a games
> studio, and we're selling invoice matching."

> "No two columns, because there's no email. Instead it shows everything it
> scored. Identity confirmed, all three findings verified, and look at the top
> one: **7 of 10**. He gave the talk himself and the sourcing is good. But the
> talk was about rendering pipelines, so **Product fit is 0 of 3** — and that
> makes it *Background only*, whatever the total says. Nothing usable, so it
> refuses to write. And it tells the rep the useful thing: try this prospect with
> a different product."

> "That's the decision I most wanted it to get right. A template generator would
> have written something here."

Then make the point explicit:

> "This cuts both ways. Take the sentence from the last prospect — *the finance
> team follows up with employees about missing expense receipts*. For receipt
> tracking that's a 3 out of 3 on product fit: collecting missing receipts is
> literally a listed capability. For invoice matching the same sentence is a 1 —
> same broad area, no invoice-to-PO connection — and Python drops it to
> background only, so it can't generate an email. One finding, two products, two
> different answers. There's a test that pins exactly that."

---

## 3 · Two people with the same name (if time) — 45 s

**Two people with the same name** → *Try this example*.

> "Two people share the name, and the company's own pages disagree — a 2023
> press release names him, the current leadership page doesn't. So it stops at
> *Confirm who you mean*, before spending anything on research, and says what to
> do: we found three possible matches, add a profile link. That's the rep's
> judgment call, not the model's."

Paste a profile URL into the box to show the form (don't submit — it would start
a live run).

---

## 4 · Past runs — 30 s

Sidebar → **Past runs**.

> "One row per run: prospect and role, company, **what we were selling**, the
> signal it ended on written out in full with its score, the status, and whether
> it was live or sample data. The run we just approved says *8 of 10 · reviewer's
> choice* — you can see at a glance that a human overruled us."

Point at an older row:

> "These say *Invoice matching (before product choice)* — they're from before the
> product selector existed. They open with their original evidence and their
> original email. Nothing was rescored retrospectively; inventing scores for old
> runs would be worse than labelling them."

Click the prospect from step 1 — it reopens in place with the same product, the
same signal, the reviewed email and the approval, read-only.

> "Reopening makes no model call. All of that came out of the database."

---

## 5 · Close — 15 s

> "Four outcomes, not one: an email to review, confirm who you mean, no strong
> signal found, and research interrupted when the provider fails — that last one
> is deliberately *not* the same as finding nothing. One product per run drives
> the search, the scoring and the email. Every reason to write is scored on the
> same rubric, the arithmetic and the gates are in Python rather than in the
> model, the rep can overrule the ranking without spending another search, and
> nothing sends."

---

### If something goes wrong live

| Problem | Say this, then |
| --- | --- |
| Search slow / hangs | "Live web research — this is the real latency." Give it ~45 s, then use the **Strong match** example. |
| **Research interrupted** appears | "That's the provider-failure path, and this is what it looks like." Click **Try again**. |
| Prospect comes back ambiguous | Use it — it's step 3 happening for real. Supply the profile link and continue. |
| Nothing is found | "That's *No strong signal found*, and it's the correct answer — and notice it suggests trying another product." Then run the **Strong match** example. |
| Only one usable signal live | Say so — the rationale switches to "it is the only finding that qualifies". Show the switch on the sample instead. |
| Scoring comes back malformed | "That's the retry path: it retries once, then records *Research interrupted* rather than guessing a score." |
| The model names a capability we don't sell | "Rejected as malformed, same path — it can't claim a product fit without naming a real capability." |
