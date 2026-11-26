# Lesson 07 — Leveling: Mid-Level vs Senior in the Behavioral Round

> **Priority:** ★★★★★ — the level you are offered is decided here more than anywhere else.
> **Estimated study time:** 50 minutes.
> **Do this after:** Lessons 01 and 02. You need your stories before you can level them.

You can pass every round and still receive the wrong offer. Interviewers do not only decide *whether*
to hire you; they decide *at what level*, and the behavioral round is where that decision is
cheapest to make. A strong mid-level story told well is a mid-level offer, however senior your
title was.

The good news: level is mostly **scope and altitude**, not talent. Both can be changed in the way you
choose and tell your stories, without changing what you did.

---

## 1. Mental Model

> **Level is the size of the problem you were trusted with, and how little you needed from others
> to solve it. It is not how hard the code was.**

Two engineers can write equally clever code. One was handed a ticket; the other noticed a failure
rate, found its cause, convinced three teams to change something, and made it stop recurring. The
second is the senior one, and nothing in the cleverness of the code tells them apart.

So interviewers listen for four things underneath every story:

| They ask themselves | A mid-level answer shows | A senior answer shows |
|---|---|---|
| **How big was the problem?** | A task someone defined | A problem *you* defined from a vague symptom |
| **How much did you need?** | Guidance on the approach | You chose the approach and could defend it |
| **How far did it reach?** | Your module, your team | Teams that did not report to you |
| **What lasted?** | The bug was fixed | The *class* of bug became harder to cause |

---

## 2. What Real Ladders Say

Levels are named differently everywhere (L4 and L5, E4 and E5, SDE-2 and SDE-3, IC3 and IC4) and
they do **not** map one-to-one between companies. Do not memorise a company's numbers. Learn the
*dimensions*, which are remarkably stable.

The clearest public example is Dropbox's open engineering career framework (version 2.9.1 at the
time of reading; the pages show no date). Paraphrased, its IC3 and IC4 software engineer levels,
the nearest equivalents of mid-level and senior, differ like this:

| Dimension | Mid-level (IC3) | Senior (IC4) |
|---|---|---|
| **Scope** | Delivers projects toward the team's quarterly goals; may lead one project | Owns the team's longer goals; defines technical solutions that raise the whole team |
| **Autonomy** | Finds solutions to ambiguous problems on their own | Delivers ongoing business impact and decides on open-ended requirements |
| **Technical judgment** | Designs components in well-scoped situations; knows when to refactor | Owns system design in an area; debugs across modules; plans safe large rollouts |
| **Influence** | Works with their own team and partners; drives cross-team work for their project | A leader whose impact extends past the team; drives cross-team initiatives |
| **Ambiguity** | Identifies the right solution to open-ended problems | Prioritises hard trade-offs and picks iterative approaches because of uncertainty |
| **Mentoring** | Helps less-experienced teammates and new hires grow | Sets the quality bar in reviews, spots others' growth areas |

*Source: Dropbox Engineering Career Framework, dropbox.github.io/dbx-career-framework, pages for
IC3 and IC4 software engineer, read 2026-11-26. Other companies' internal rubrics are not public;
treat any specific claim about them with suspicion.*

Notice what is **not** in the senior column: "writes harder code", "knows more algorithms". The
difference is about owning outcomes and moving other people.

---

## 3. The Same Story at Two Levels

The vocabulary shift is the clearest tell. Take the same project.

**Told at mid-level**

> "My manager asked me to migrate our billing database, so I wrote the migration scripts and moved
> the tables."

Nothing is wrong with it. It also contains no decision, no one disagreeing, and no result.

**Told at senior level**

> "Month-end billing was causing CPU spikes on our main database because of lock contention. I
> wrote a short design doc comparing three options on write throughput, operational cost and
> migration risk, and ran the review with the data and infrastructure leads. Partitioning the
> existing database won — it met the throughput target without an application rewrite — so I
> planned a phased dual-write migration with a rollback step at each phase. We finished with no
> customer downtime. The thing I would change: I should have load-tested with month-end volumes
> before the review, not after."

Count what changed. It is the same work, but the second version contains: a **problem found, not
assigned**, a **comparison with criteria**, **other teams in the room**, a **risk plan**, a
**measured outcome**, and an **unprompted mistake**. Every one of those is a level signal, and
none requires a bigger job.

> **Use a real number from your own work** wherever the story has one (throughput, error rate,
> latency, hours saved). If you did not measure it, say so and say what you would measure. An
> invented figure collapses at the first follow-up.

---

## 4. Four Artifacts That Signal Senior

Weave these into your stories naturally. Each is cheap to describe and proves something specific.

| Artifact | What it proves | The minimum you can say about it |
|---|---|---|
| **A design doc or RFC** | You decide in writing and build agreement before building | "I wrote up the options and the recommendation, and the review changed X" |
| **A decision matrix** | You compare options on criteria, not on taste | "We scored three options on throughput, cost and migration risk" |
| **A rollout and rollback plan** | You plan for failure before shipping | "Each phase had a check and a way back" |
| **A blameless postmortem** | The organisation learns, not only you | "We found the root cause, and added an automated guardrail so it can't recur" |

**A weak mention vs a strong one.** *"We did a design review."* tells them nothing. *"The review
changed my recommendation, because security pointed out a data-residency constraint I'd missed"*
proves you listen, which is a senior signal by itself.

---

## 5. How People Get Down-Levelled

These are the patterns that turn a senior candidate into a mid-level offer. All are about telling,
not doing.

| Pattern | What the interviewer hears | The fix |
|---|---|---|
| **All "I did what I was told"** | You execute, you don't originate | Start the story with the symptom you noticed, not the task you received |
| **Impact only inside your module** | Your reach stops at your team | Name one team outside yours that you needed and how you got them |
| **No disagreement anywhere** | You avoid or lose conflicts | Include one real disagreement and how it resolved, steelmanning the other side |
| **Heroics instead of systems** | You rescue, you don't prevent | End with what changed so the problem does not return |
| **Mentoring as "I answered questions"** | You are helpful, not multiplying | Describe what you changed in how others work: a review practice, a template, a person you grew |
| **Technology tour** | Cleverness is the point | Cut stack detail until a decision and its reason remain |

> **One honest caution:** if every story you have is a mid-level story, no wording fixes that.
> Do the self-test in §6, find your gap, and prepare the *true* senior-scope stories you do have.
> Many candidates own one and never tell it because it "wasn't official".

---

## 6. Calibrate Yourself

Take each of your core stories from Lesson 02 and answer five questions. Score one point per yes.

1. Did **you** identify or define the problem, rather than receive it?
2. Did you compare **at least two options** and can you say why you chose one?
3. Did you need **people outside your team**, and did you win their agreement?
4. Did something **change permanently** (a guardrail, a process, a design), not just a one-off fix?
5. Do you volunteer **what you would do differently**?

| Score | What it tells you |
|---|---|
| 0 to 1 | Task execution. Strong mid-level at best, as told |
| 2 to 3 | Senior in places. Find the missing points; they are usually in your telling |
| 4 to 5 | Senior scope. Make sure the interviewer hears every point in under two minutes |

You need **three or more stories at 4 or higher** to be calibrated for senior. Fewer means the
gap is stories to find, not words to polish.

---

## 7. Drills

1. In your own words, what is the difference between *how hard the code was* and *level*?
2. Why do level names (L4, E5, IC4, SDE-3) not transfer between companies, and what transfers?
3. List the six ladder dimensions in §2 and give one sentence on how senior differs on each.
4. Rewrite this at senior altitude: *"I was assigned to add retries to the payment service."*
5. Name the four senior artifacts and what each proves.
6. Why is "we did a design review" a weak mention, and how do you make it strong?
7. Which down-levelling pattern from §5 do you recognise in yourself, and what is the fix?
8. If you have no story scoring 4 or more, what do you do, and what do you *not* do?

---

## 8. Homework

**Part A** — Score every story in your Lesson 02 inventory with the five questions in §6. Write the
scores down.

**Part B** — Pick your highest-scoring story. Rewrite its opening so it starts from the *symptom you
noticed*, not the task you were given. Keep it under 250 words, then tell it aloud with a timer.

**Part C** — For the lowest-scoring story, find the one missing point. Is it that you did not
compare options, or that you never named the outside team? Fix the telling if the fact is true,
and drop the story if it is not.

**Part D** — Ask someone who has worked with you for a year: "Which of my projects reached beyond
our team?" Their answer often reveals a senior story you had stopped seeing as one.

---

## Sources

- Dropbox Engineering Career Framework (v2.9.1), IC3 and IC4 software engineer pages,
  dropbox.github.io/dbx-career-framework. Read 2026-11-26; the pages show no date.
- Will Larson, *StaffEng* guides index (staffeng.com), for the Staff-level dimensions this lesson
  deliberately stops short of. Read 2026-11-26 (index only).

*Last reviewed: 2026-11-26. This lesson states no compensation figures.*
