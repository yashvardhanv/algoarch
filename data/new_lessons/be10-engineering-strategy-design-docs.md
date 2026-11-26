# Lesson 10 — Writing Engineering Strategy and Design Docs

> **Priority:** ★★★☆☆. The written decision is the clearest Staff-level artefact you can show, and the one interviewers probe when they ask "how did you get agreement?"
>
> **Study time:** 70 minutes. **Do this after:** Lesson 09 (what Staff engineers do) and Lesson 07, whose section on artifacts only names the design doc. This lesson is about writing one that works and then pulling a strategy out of several.
>
> **Level:** advanced. Optional for a crash plan.

Lesson 07 told you to mention a design doc because it proves you decide in writing. It did not say what makes one good, when not to write one, or what to do when the same argument keeps coming back through five different documents. That recurring argument is the raw material of an engineering strategy. This lesson covers the document that records one decision (the design doc), the document that records the pattern across decisions (the strategy), and the longer-horizon document above that (the vision), with the process the published sources recommend and worked illustrative examples.

> **What this lesson will not do.** It does not describe any company's internal template as fact; it uses the one published account of design docs at Google and one published guide on strategy, named in Sources. Every document extract below is **illustrative**: invented, not from a real system or company. It states no compensation figures.

---

## 1. Mental Model

> **A design doc records one decision and the trade-offs behind it. A strategy records what several decisions had in common, with the reasoning, so the next decision costs less. A vision projects several strategies a few years forward. Write them in that order, never the reverse.**

Will Larson's guide on strategy gives the recipe in two sentences: write five design documents and pull the similarities out, that is your strategy; write five strategies and forecast their implications two years ahead, that is your vision. The claim underneath is that good strategy is specific and a little boring, and that you earn it from detailed, real decisions rather than inventing it from a blank page.

| Document | Question it answers | Written from | Typical length | Who reads it |
|---|---|---|---|---|
| **Design doc** | What are we building, and why this way and not another? | The problem in front of you | A page or three for a mini doc; Google's article says ten to twenty pages is the sweet spot for a larger project | The people who must agree, build or rely on it |
| **Strategy** | How do we decide this kind of question here, and why? | Several design docs and the arguments that repeated | A few pages | People about to write the next design doc |
| **Vision** | What should the technical shape of the company look like in two or three years? | Several strategies and their contradictions | One to two pages, per Larson | Mostly the people writing strategies |

The audience of a strategy is mostly future authors. That is why its success is quiet, a point §6 returns to.

---

## 2. Recognise What to Write

| If the situation is... | Reach for | Why |
|---|---|---|
| The approach is unclear, contentious or costly to change, and several people must agree | A design doc | Cheapest moment to find a flaw is before code exists |
| The same debate has happened three or four times in different reviews | A strategy | You are paying the discussion cost repeatedly |
| Two of your strategies pull against each other, and the future is hazy | A vision | It reconciles them over a longer horizon |
| The solution is obvious and nobody would disagree | Nothing; write the code | A doc that only says how it will be implemented is an implementation manual |
| A small change inside an agreed design | A mini doc of one to three pages, or a comment in the existing doc | Same steps, tighter scope |

Larson's rules of thumb for requiring a design doc: the work will be built on by many later projects, it meaningfully affects users, or it will take more than a month of engineering time. The Google article's test is different and sharper: write one when the solution is ambiguous, whether from problem complexity or solution complexity. Use whichever test fits; both agree that when the solution is not ambiguous, the doc is overhead.

---

## 3. The Design Doc: Anatomy and What Each Part Is For

The Google article says design docs are informal and rule number one is to write them in whatever form suits the project, then describes a structure that has proved useful. The sections below follow it, with what each section is really testing.

| Section | What goes in it | What a reviewer checks | Common failure |
|---|---|---|---|
| **Context and scope** | Objective background facts, briefly; link detail rather than paste it | Can a new reader get oriented without asking you? | A requirements dump, or opinions disguised as background |
| **Goals and non-goals** | What the system must do, and things that could reasonably have been goals but are chosen not to be | Is each non-goal a real option you declined, not a negated goal? | "The system shouldn't crash" listed as a non-goal |
| **The actual design** | An overview first, then detail, focused on the trade-offs | Could a competent engineer disagree with a statement here? | A description of what will be built with no reasons |
| **APIs and data storage** | The parts relevant to the design and its trade-offs | Is it the interface, not a pasted schema? | Copying full interface or schema definitions that go stale |
| **Alternatives considered** | Designs that would have reasonably met the goals, and the trade-off that lost each | Would a reader who thought of option B find it answered? | A straw man, or no section |
| **Cross-cutting concerns** | Security, privacy, observability, and whatever your team standardises | Was each considered, even if the answer is "no impact"? | Left to the end, then forgotten |

Two sections carry most of the value.

**Non-goals.** A non-goal is something that could plausibly be a goal and is explicitly not. The Google article's example is full transactional guarantees for a database: you would certainly want to know whether that is in or out. A non-goal protects the doc from scope creep and tells reviewers what not to argue about.

**Alternatives considered.** The Google article calls this one of the most important sections, even though it is fine to be brief about the losers. It shows why the chosen design is best given the goals and answers the question the reader is already forming.

**Length and code.** Design docs should rarely hold code or pseudo-code except to describe a novel algorithm; link a prototype instead. Brevity matters because busy people have to finish reading.

---

## 4. Lifecycle: Where Docs Go Wrong in Practice

The Google article names four phases: creation and rapid iteration, review, implementation and iteration, and maintenance and learning. Each has a failure that Staff-level stories can expose.

1. **Creation.** Larson's advice is to start from the problem, because a clear problem statement makes solutions more obvious; keep the template minimal, because overloaded templates discourage people from writing at all; and gather perspectives widely but write alone, since most people write better than they edit as a group.
2. **Review.** The Google article notes reviews add value and also risk becoming overhead. Its stated main value is catching issues while changes are still cheap, and ensuring cross-cutting concerns are covered. It suggests getting the crucial feedback directly rather than blocking on a wider review.
3. **Implementation.** Plans collide with reality. If the system has not shipped, update the doc; if you add amendments elsewhere, link them from the original so a future maintainer can follow the trail.
4. **Maintenance and learning.** Both sources suggest re-reading your own design after the system exists and studying where it deviated from the plan. Keep a short deviation ledger: what changed, what you believed then, what you know now.

Larson adds one more rule: prefer good over perfect. Do not hold a colleague's design to the standard of your best one; push it to good.

> **Interview angle.** "The review changed my recommendation" (Lesson 07) is a senior signal. A Staff-level addition is: "I kept a ledger of where the build departed from the doc, and it changed how I write the next one." That shows you treat your own judgement as something to calibrate.

---

## 5. From Design Docs to Strategy

When your organisation has five design docs, read them together. Look for the decision that came up repeatedly, especially the ones that were hard to agree on. Rather than restarting that argument in each review, record how you decided and why.

Larson's definition borrows from *Good Strategy, Bad Strategy*: a strategy is a diagnosis plus guiding policies, and the "coherent action" part lives in the design docs. His practical rules:

| Rule | What it means | A check you can apply |
|---|---|---|
| **Start where you are** | Waiting for missing information does not work; write what you have and fix it | Is there a draft yet? |
| **Write the specifics** | Write until you start to generalise, then stop; if you cannot be specific, write more design docs first | Could two engineers interpret this sentence differently? |
| **Be opinionated** | A strategy with no opinion gives no help deciding | Does it rule something out? |
| **Show your work** | State the rationale, so others can change the policy when the context changes | Would the policy still be understandable in two years? |

The first test of a strategy sentence is whether it tells someone what to do on Monday. "We value reliability" is not a strategy. "A service that holds data other services read must declare an owner and a rollback path before it takes production traffic, because the last three incidents each involved an unowned data store" is.

**Strategies can be small.** Larson says some of the best strategies feel too obvious to write, such as when to write a design doc or which database fits which use case, and that casual strategies are fine because you can deprecate one that goes unused.

**Vision.** Five strategies extrapolated over two to three years become a vision. Larson's focus points: two to three years out, grounded in your business and users, optimistic rather than audacious, concrete and specific (details illustrative rather than binding), and one to two pages. Do not judge a vision by the initial excitement; his proposed test is to compare a design doc from two years ago to one from last week and see whether the quality improved.

---

## 6. Worked Examples (all illustrative)

### 6.1 A mini design doc, annotated

*Illustrative scenario: a team that sends email and push notifications wants retries for failed sends.*

> **Context and scope.** Sends can fail transiently. Today a failed send is dropped after one attempt. Out of scope: rewriting the provider integration.
>
> **Goals.** Redeliver sends that fail for transient reasons. Avoid sending the same message twice from the user's point of view.
> **Non-goals.** Guaranteeing delivery for permanently invalid addresses. Ordering across different message types. (Both could reasonably be goals; we decline them.)
>
> **Design.** A retry queue keyed by message id; an attempt counter; exponential delays with a ceiling; a bounded number of attempts; a dead-letter store for exhausted sends that an operator can inspect.
>
> **Alternatives considered.** (A) Retry inline in the request path: simplest, but it holds user-facing requests open and multiplies load during provider outages. (B) Let the provider's own retry handle it: removes our code, but we lose control of attempt limits and cannot tell users the status. We chose the queue because the goals require visibility and bounded behaviour.
>
> **Cross-cutting.** Privacy: the queue stores message ids, not message bodies. Observability: attempt counts and dead-letter depth are metrics with an alert on growth.

What this extract does that a weak doc does not: the non-goals are real options declined; alternatives are specific and each loses on a named trade-off; the design has a reason attached to each choice; cross-cutting concerns have an answer.

### 6.2 Five docs to one strategy

*Illustrative scenario: five docs in a year each argued about whether a particular store may be the system of record.*

| Doc | The recurring argument | How it was settled that time |
|---|---|---|
| Notifications retry | Can a queue be the only copy of unsent work? | Yes, with a dead-letter store and replay |
| Profile cache | Can a cache be the only copy of anything? | No |
| Search index | Can an index be the only copy? | No; rebuildable from the primary |
| Audit log | Can a log be the primary record for compliance? | Yes, append-only with retention rules |
| Session store | Is losing a few seconds of state acceptable? | Yes |

A strategy extracted from the pattern might read:

> **Diagnosis.** We keep re-arguing which stores may hold the only copy of data, because we lack a rule.
> **Guiding policy.** A store may be the only copy if (a) it is append-only or transactional, (b) it has a documented recovery path, and (c) an owner is named. Caches and indexes must be rebuildable from another source and never accepted as the record. Exceptions need a short doc.
> **Why.** In four of the five reviews the deciding question was recovery, not speed. Writing the rule once saves one meeting per future design.

It is opinionated (it rules things out), specific (three conditions) and shows its work (the pattern in the docs). The tests from §5 pass: two engineers cannot easily read it differently. What it deliberately does not do: pick a database product. Strategy guides the trade-off, and the design docs choose.

### 6.3 Rewriting a generic strategy into a real one

| Generic (illustrative) | What is wrong | Rewritten |
|---|---|---|
| "We will build scalable, resilient services." | Nobody can disagree, so nobody can decide | "New services must declare a load limit and a shed behaviour in their design doc; services without both do not go to production." |
| "Teams should use the right tool for the job." | Delegates the question the strategy exists to answer | "Default to the two approved data stores; a third needs a doc that names the capability the first two lack." |
| "We will modernise the platform." | No diagnosis, no policy | "Diagnosis: builds take longer than the team can iterate on. Policy: reduce build time before adding features to the platform; measure median build time monthly." |

---

## 7. Pitfalls

1. **A strategy from a blank page.** Without real design docs behind it, it will be generic. Wait, or write the docs.
2. **A policy without a reason.** Without context it becomes incomprehensible, and cannot be adapted when the context shifts.
3. **Non-goals that are negated goals.** "Do not crash" is a requirement, not a non-goal.
4. **No alternatives section, or a straw man.** The reader is already thinking of option B.
5. **Pasting schemas and interfaces.** They go stale; describe what the design depends on.
6. **An overloaded template.** If the template discourages the doc, the doc will not be written.
7. **Perfect over good.** Particularly when reviewing a colleague: push to good, not to your best.
8. **Measuring a vision by applause.** The audience is small and the response is usually muted; measure by the quality of later documents.
9. **A design doc for an obvious change.** Write the code.
10. **Never going back.** Not re-reading your doc after the system exists throws away the main learning.

---

## Drills

1. In one sentence each, distinguish a design doc, a strategy and a vision, and say which is written first.
2. What is a non-goal? Give an example from a system you know that is a real non-goal, and one that is only a negated goal.
3. Why does the Google article treat "Alternatives considered" as one of the most important sections even though losing options may be treated briefly?
4. When should you not write a design doc? Give the signal that a doc has become an implementation manual.
5. State Larson's "five and five" recipe. What problem does basing a strategy on real design docs solve?
6. Rewrite this as a specific strategy sentence, keeping the facts illustrative: "We should be careful with data migrations."
7. Why does Larson suggest gathering input widely but writing alone? What is the risk of editing a group draft?
8. How would you measure whether a vision is good, given that the initial reaction is usually muted?

---

## Homework

**Part A.** Write a mini design doc of one to two pages for a real change you made or could make. Sections: context, goals, non-goals (at least two real ones), design, alternatives (at least two, each with a named losing trade-off), cross-cutting concerns. Have one colleague read only the non-goals and alternatives and say what they would argue about.

**Part B.** Find three design docs, yours or your team's, and list the decisions that came up in more than one. If any repeated, draft a diagnosis, a guiding policy and a why. If none repeated, write what would have to be true for one to.

**Part C.** Take a strategy-sounding line from your company's materials and rewrite it so two engineers cannot interpret it differently. If you cannot, note which specifics are missing and which documents would supply them.

**Part D.** Start a deviation ledger for one finished project: the three biggest differences between the doc and the build, what you believed then, what you know now. Use one of them as the "what I would change" sentence in a Lesson 02 story.

---

## Sources

All read on 2026-11-26.

- Will Larson, "Writing engineering strategy", staffeng.com/guides/engineering-strategy, read in full. Used for: the five-docs-to-strategy-to-vision recipe, when to write strategy, the advice on writing design docs and strategies, and the vision focus points. The recipe and rules are his recommendations, not measured results.
- "Design Docs at Google", industrialempathy.com/posts/design-docs-at-google, read in full. Used for: the anatomy, goals and non-goals, alternatives considered, cross-cutting concerns, the ten-to-twenty page guideline and mini docs, when not to write one, and the lifecycle phases. The text I read describes practice at Google as of its writing; the page shows no date in the text I read, and I did not confirm the byline, so this lesson names no author and draws no claim about current Google practice.
**Not consulted:** *Good Strategy, Bad Strategy* (cited by Larson; I rely only on his description of its diagnosis and guiding-policy parts), the other design doc references Larson links (the Markdown and Git approach, and the remote-culture article), and the two example strategies he links. Examples of real strategies were not read.

*Last reviewed: 2026-11-26. This lesson states no compensation figures.*
