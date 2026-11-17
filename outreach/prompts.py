"""Prompt templates. Kept in one place so the reviewer can read the rules.

Every prompt that needs to know what is being sold takes a ``Product`` and
renders it through ``seller_block``. Nothing here hard-codes an offering, so
selecting a different product on the form genuinely changes the research
question, the scoring and the draft.
"""

from __future__ import annotations

from .schema import Product

GROUNDING_RULES = """
Hard rules:
- Use only what the search results actually say. Never invent a quote, a date,
  a URL, a publisher, or a search result.
- If you did not find something, say so plainly. An empty answer is correct and
  useful; a plausible-sounding guess is a failure.
- Do not speculate about what a company needs, buys, or struggles with.
""".strip()


def seller_block(product: Product) -> str:
    """The complete, and only, description of what we are selling this run."""
    return f"""
What we sell on this run (this is the complete and only description):
  Product: {product.name}
  Sold to: {product.target_users}
  What it does: "{product.description}"

Its capabilities, in full — there are no others:
{product.capability_lines()}

You must not attribute any other capability, customer, metric, or saving to it,
and you must not refer to any other product.
""".strip()


# ---------------------------------------------------------------------------
# Stage 1 -- identity
#
# Identity is deliberately product-blind: the question is only whether we have
# found the right human being. What they might want comes later.
# ---------------------------------------------------------------------------
IDENTITY_SEARCH = """
Find public evidence about who this person is and where they currently work.

Person: {name}
Stated company: {company}
{hints}

Search for their current employer and role. Report:
1. Every distinct person you find matching this name in a professional context,
   with their employer and role, and where that came from.
2. Whether any source connects this name to "{company}".
3. Any disagreement between sources about the current employer (for example an
   older page showing a previous employer, or a newer announcement showing a move).

{rules}
""".strip()

IDENTITY_JUDGE = """
You are deciding whether the research below identifies ONE specific person at a
specific company, well enough for a salesperson to write to them.

Person asked for: {name}
Company asked for: {company}
{hints}

Research summary (a search-result summary written by a model, not source text):
---
{research}
---

Sources cited by the search:
{sources}

Decide one status:
- "confirmed": the evidence connects this name to {company} and there is no
  meaningful competing candidate or employer conflict.
- "ambiguous": several different people fit the name, OR sources disagree about
  this person's current employer, OR the only evidence is weak/indirect.
- "not_found": no credible public evidence about this person at all.

Return JSON only:
{{
  "status": "confirmed" | "ambiguous" | "not_found",
  "confidence_reason": "one sentence citing what the evidence shows",
  "ambiguity": "if ambiguous: one or two sentences a salesperson can act on, naming the competing options or the conflict. Empty string otherwise.",
  "candidates": [
    {{"description": "name, role, employer", "why": "what source suggests this", "url": "url from the list above or empty"}}
  ]
}}
Use at most 4 candidates. Only include a url that appears in the source list.
""".strip()

# ---------------------------------------------------------------------------
# Stage 2 -- candidate signals
#
# The SEARCH prompt is product-aware: knowing what we sell is what makes the
# search look in useful places. The EXTRACT prompt is deliberately NOT, so the
# facts we keep are shaped by the sources rather than by what we hope to find.
# ---------------------------------------------------------------------------
RESEARCH_SEARCH = """
Research what this person and their team are publicly doing right now.

Person: {name}
Company: {company}
{role_line}
{hints}
{identity_note}

{seller}

Look for, in this order of usefulness:
1. Public evidence about the specific work our capabilities above touch — the
   team's own process pages, policies, active job postings describing those
   tasks, or the person describing that work themselves.
2. The person's own public statements more generally — interviews, podcasts,
   conference talks, bylined posts, quotes in press releases.
3. Evidence of what their team is doing — active job postings for their team,
   official company pages about their function, process announcements.
4. Company news that plausibly touches their responsibilities — funding,
   expansion, acquisitions, new systems, new markets, new entities.

Knowing what we sell tells you where to look. It does not tell you what is
true: do not report that this company does something because our product would
suit them. Report only what a source says.

Prefer official company pages, active job postings, announcements and interviews.
For each thing you find, state: the specific fact, who published it, the URL, and
the date if the page gives one.

{rules}
""".strip()

RESEARCH_EXTRACT = """
Turn the research below into at most {max_findings} separate, specific findings.

Person: {name}
Company: {company}
{role_line}

Research summary (model-written summary of search results -- NOT source text):
---
{research}
---

Sources the search cited (use these URLs and nothing else):
{sources}

A good finding is one concrete, checkable fact. Bad: "the company is growing".
Good: "Posted a job opening for an Expense Operations Analyst in Pune on 3 March".

Record what the sources say. Do not judge how useful a fact is, do not rank the
findings, and do not leave out a fact because it looks unhelpful — something
else decides that later.

Return JSON only:
{{
  "findings": [
    {{
      "claim": "one sentence stating the specific fact, in your own words",
      "publisher": "who published it, e.g. 'Acme careers site' or 'TechCrunch'",
      "url": "exact URL copied from the source list above",
      "date": "date the source gives, as written, or empty string if none",
      "kind": "job posting | announcement | interview | official page | news | other",
      "quote": "a short verbatim sentence from the source if the research clearly contains one, otherwise empty string"
    }}
  ]
}}

Rules:
- Every finding must have a url copied exactly from the source list. Drop any
  finding you cannot attribute to one of those URLs.
- Leave "date" empty rather than guessing. Leave "quote" empty unless you are
  reproducing words verbatim.
- Return {{"findings": []}} if the research contains nothing specific.
""".strip()

# ---------------------------------------------------------------------------
# Stage 3 -- score every candidate signal against a fixed rubric
#
# One structured call scores all candidates at once, keyed by finding_id.
# Python validates the ids, the ranges and the named capability, totals the
# scores and sorts; the model never decides the winner and never sees a
# running total.
# ---------------------------------------------------------------------------
SIGNAL_SCORE = """
Score each candidate finding below as a reason to contact this prospect now
about this one product.

{seller}

Prospect: {name}{role_line} at {company}

Candidate findings (each is already verified against the source shown):
{findings}

Score every finding separately, using this exact 10-point rubric. Give the
integer that the source actually establishes -- not the one that would make the
finding look useful.

Product relevance, 0-3
  0 = no demonstrated connection to a listed capability
  1 = same broad business area only
  2 = a related workflow is described, but the exact task is unclear
  3 = the source explicitly describes a task this product handles

Prospect relevance, 0-3
  0 = no demonstrated connection to this person's work
  1 = company-wide development
  2 = concerns their team or function
  3 = evidence shows the person owns or publicly discussed this initiative

Evidence quality, 0-2
  0 = unsupported or contradicted
  1 = credible secondary reporting supports the claim
  2 = a direct source supports the claim, such as the company's own posting or
      the person's own statement

Timeliness, 0-2
  0 = stale or undated with no evidence of current relevance
  1 = dated and plausibly relevant
  2 = demonstrably current, such as an active job posting

Product relevance is about THIS product only:
- Score 2 or 3 only when you can name which capability from the list above
  connects to which task the source actually describes. Put that capability in
  the "capability" field, copied exactly from the list, and say in the reason
  which source-supported task it connects to.
- A job title alone proves nothing. Someone working in finance, procurement or
  payables does not thereby need this particular product; a finance title is
  not evidence of any specific task.
- A company being large, funded, growing or newsworthy is not a connection to
  what we sell. That is 0.
- If no listed capability connects, score 0 or 1 and leave "capability" empty.
  That is a correct and useful answer.

Score what the source establishes, and nothing more:
- A recently published article about an old event does NOT automatically earn 2
  for timeliness. Date the event, not the page.
- A job title alone does NOT prove the person owns a particular initiative.
  That is a 3 for prospect relevance only when the evidence shows them owning
  or publicly discussing this specific thing.
- You are scoring the strength of an outreach angle. You are NOT predicting
  whether they will buy, and you must not reason about that.

Return JSON only, with one entry per finding_id given above and no others:
{{
  "scores": [
    {{
      "finding_id": "f-1",
      "product_relevance": 0,
      "prospect_relevance": 0,
      "evidence_quality": 0,
      "timeliness": 0,
      "capability": "the capability from the list above that connects, copied exactly, or an empty string",
      "product_relevance_reason": "at most 20 words naming the capability and the source-supported task it connects to",
      "prospect_relevance_reason": "at most 15 words on what the source shows",
      "evidence_quality_reason": "at most 15 words",
      "timeliness_reason": "at most 15 words"
    }}
  ]
}}

Every finding_id above must appear exactly once. Do not invent a finding_id, do
not merge findings, and do not add any other field.
""".strip()

# ---------------------------------------------------------------------------
# Stage 4 -- draft
# ---------------------------------------------------------------------------
DRAFT_EMAIL = """
Write a short first-contact email from a salesperson to this prospect.

{seller}

To: {name}{role_line} at {company}

The one signal this email is built on:
  Fact: {claim}
  Published by: {publisher}{date_line}
  Source: {url}
{quote_line}
{capability_line}
Why it was chosen: {selection_reason}

Write it so it reads like one person writing to another: plain words, no
marketing voice, no bullet lists, no "I hope this finds you well", no flattery.
60-120 words in the body. Reference the fact specifically enough that it could
not have been sent to anyone else.

What you may and may not say:
- You MAY note the fact and ask how they handle something related to it.
- You MAY NOT claim or imply they have a backlog, are losing money, are making
  errors, are inefficient, or want new software. A source describing a task
  supports asking how the team handles that task today. It does not establish
  that anything is going wrong.
- You MAY NOT invent customers, metrics, savings, mutual contacts, or product
  features beyond the capabilities listed above.
- Write about one capability, the one named above if there is one. Do not list
  the others.
{quote_rule}

End the body with exactly one question mark, in the final sentence.

Return JSON only:
{{"subject": "under 60 characters, specific, no colon-heavy marketing phrasing",
  "body": "the email body including a greeting line and a sign-off of '[Your name]'"}}
""".strip()

QUOTE_RULE_ALLOWED = (
    '- You MAY quote the verified sentence above verbatim inside quotation marks. '
    "Copy it exactly or do not quote at all."
)
QUOTE_RULE_FORBIDDEN = (
    "- There is no verified quote for this finding, so you MUST NOT put anything "
    "in quotation marks. Paraphrase the fact instead."
)
