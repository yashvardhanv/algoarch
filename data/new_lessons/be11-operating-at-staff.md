# Lesson 11 — Operating at Staff: Quality, Alignment and Presenting to Executives

> **Priority:** ★★★☆☆. These three skills decide whether Staff-level scope turns into results, and they are what "influence without authority" questions are really about.
>
> **Study time:** 75 minutes. **Do this after:** Lessons 09 and 10. Lesson 10 gave you the written decision; this lesson is about getting it adopted, keeping quality from decaying, and getting an executive to engage with it.
>
> **Level:** advanced. Optional for a crash plan.

A Staff engineer's ideas run into three obstacles that code review never taught: the codebase's quality drifts and nobody owns the drift, the authority you operate under is borrowed and can be withdrawn, and the people who decide resources consume information in ways you did not choose. This lesson covers one published approach to each, builds worked illustrative examples, and shows how to turn them into behavioral answers.

> **What this lesson will not do.** It does not claim these approaches are proven by measurement. They are one practitioner's recommendations from his own experience and interviews, and the lesson says so where it matters. The scenarios are **illustrative**, not records of any company. It states no compensation figures.

---

## 1. Mental Model

> **At Staff you do not have enough authority to order change, so you choose the cheapest mechanism that will work, in the right order, and you stay aligned with whoever lends you your authority.**

Three connected ideas, all from Will Larson's *Staff Engineer* guides, which are the only source behind this lesson:

| Idea | The claim | The practical consequence |
|---|---|---|
| **Quality is a staircase** | Start with the lightest tool and move to heavier ones only when the lighter ones are overwhelmed | Fix hot spots before you write a company-wide process |
| **Authority is loaned** | Organisational authority is lent by a more senior sponsor, usually your manager, and depends on staying aligned with them | Never surprise your manager, and feed them context |
| **Executives preprocess reality** | Each executive is very good at consuming information in one way, so your presentation fails if it is shaped for someone else | Write a structured document, pre-align, and learn what this executive needs |

---

## 2. Recognise the Situation

| If the prompt or situation says... | The skill | Start with |
|---|---|---|
| "Tell me about improving code quality across teams" | Quality staircase | Measure the specific problem, then the cheapest fix |
| "How did you roll out a new practice?" | Best-practice rollout | One practice at a time, piloted with a few engaged teams |
| "Tell me about disagreeing with leadership" or "influencing without authority" | Alignment | What your sponsor wants, what they know, what would surprise them |
| "Tell me about presenting to senior leaders" | Executive communication | Why you are in the room: planning, reporting, or resolving misalignment |
| Your manager changed, or priorities shifted | Alignment | Re-establish how you partner; assume your standing may reset |

---

## 3. Managing Technical Quality

### 3.1 Start by dropping the villain

Larson's opening claim is that low technical quality is usually not a crisis caused by bad engineers. It is the expected state: engineers make reasonable decisions when they make them, a successful company raises its quality bar over time, so most earlier decisions fall below the current bar. Closing the gap is routine leadership work, not blame. This matters in an interview because answers that assign blame to a previous team read as junior.

### 3.2 The staircase

He lists seven approaches in the order to try them: fix hot spots; adopt best practices; prioritise leverage points; align technical vectors; measure quality; create a quality team; run a quality program. He also says real organisations do not climb linearly: you may hot-spot, roll out a practice, set up a review, abolish it and return to hot-spotting. Pick the cheapest tool likely to work.

| Step | Idea | A test for "am I at the right step?" |
|---|---|---|
| **Hot spots** | Act like a performance engineer: measure where most of the problem is and fix precisely that. Prefer fixing a design that causes errors over rolling out a process | Did I measure where the problem concentrates before choosing a fix? |
| **Best practices** | Evolve a practice with a few engaged teams, improve the documentation, then widen. Limit yourself to a single new practice rollout at a time | Is a practice already half-adopted? If so, do not start another |
| **Leverage points** | Invest extra in interfaces, stateful systems and data models, where change is expensive later. These need less organisational alignment than a vision does | Is this one of the three things hardest to change later? |
| **Technical vectors** | Align the direction of many decisions: direct feedback, strategy, tooling that encodes the approach, onboarding, organisational structure, and architecture reviews last | Have I tried a conversation before a process? |
| **Measure** | Define quality precisely enough to count it, then instrument it | Can I state three specific, countable properties? |
| **Quality team** | A dedicated team, starting small, driven by metrics and users | Is the backlog of important quality work bigger than part-time effort can handle? |
| **Quality program** | A sponsored, program-managed push across teams | Do I have a sponsor and a program owner? |

Two of Larson's cautions deserve emphasis. First, a rolled-out process is not an adopted process: he tells a story of a mandate that was announced, documented and declared a success, while nobody changed what they did. Second, process is a human-change cost, so reach for it after trying to fix the specific problem directly.

### 3.3 Hot spots in practice

His example worth remembering: instead of training a whole team to write better tests, you might delete the single test file where nearly all the failures occur. The skill is measurement first, process second.

*Illustrative scenario.* A team's continuous integration is flaky. The reflex is a "tests must pass twice" rule. The hot-spot version is: list the last month of failed runs, group them by test, find that one integration test accounts for most failures, and fix or quarantine that test. The rule would have slowed everyone to address a problem that lived in one place.

### 3.4 Leverage points

Larson's three: interfaces (contracts that hide the implementation and expose essential rather than accidental complexity), stateful systems (the hardest part of any system to change, more so once security, privacy and compliance apply), and data models (where interface meets state; a good one prevents invalid states and tolerates evolution). His practical advice: integrate half a dozen clients against a mocked implementation before committing to an interface, represent half a dozen real scenarios before settling a data model, and exercise failure modes and consistency behaviour of a stateful system under production-like benchmarks, then write it up and socialise the doc.

### 3.5 Measuring quality

Counting pull-request size or file length is only a proxy. His suggestion is to define quality precisely for your own codebase, with measurable components. Examples he lists include: what share of code is statically typed, how many files have tests, how narrow the public interfaces are, how many endpoints do all state changes inside one transaction, and how many files change in a large share of pull requests. Instrumentation is the hard part and the biggest friction.

---

## 4. Staying Aligned With Authority

### 4.1 Why

Titles bring organisational authority, and that authority is lent by a more senior authority, usually your direct manager. What is lent can be withdrawn, so keeping it depends on remaining aligned. Larson also says the safety net that guided you to Senior fades after Staff: you are now partly responsible for setting your manager and team up for success.

His practices for aligning upward, restated as habits:

| Habit | What you do | Why |
|---|---|---|
| **Never surprise your manager** | Treat each surprise as an incident to learn from | Surprises break a leader's ability to juggle many things and raise doubt about whether they are in charge |
| **Do not let your sponsor surprise you** | If they are not good at relaying information, facilitate it: a weekly note, a shared channel thread, asking in 1:1s | Your work depends on context they may forget to pass on |
| **Feed their context** | Tell them what the wider organisation is saying: friction with a new policy, a tool not scaling. Say you are informing, not handing them a problem, and add data where possible | It raises their bandwidth and reduces their surprises |
| **Merge your view with leadership's, deliberately** | Know where your values differ from the organisation's and advocate without being ejected from the room | You keep the perspective that made you effective without losing your seat |

He is explicit that "managing up" done well is about increasing bandwidth and reducing friction, and that the destructive version is controlling information or hiding problems.

### 4.2 Illustrative scenario

*You disagree with a reorganisation that will split a platform team.* A weak response: argue in a leadership meeting, lose, then complain. A better sequence: first ask your manager what problem the reorganisation is solving; send them, privately, the two pieces of data that bear on the risk; state your concern once, in writing, with the alternative; and if the decision stands, agree and commit, then watch the specific risk you named and report on it later. The point is to stay in the room, and the answer you would give in a behavioral round is the one that shows both a clear opinion and the discipline to commit.

---

## 5. Presenting to Executives

### 5.1 Why it is hard

Larson's argument: most executives are not poor; they are very good at one way of consuming information (a pattern matcher who asks many detailed questions, or someone who ignores anything not tied to data) and the communication systems around them are tuned to that. Present in the wrong form and you get miscommunication neither side can explain. You often get no second chance before the decision.

### 5.2 Know why you are in the room

He says that with an executive it is almost always one of three things: planning, reporting status, or resolving misalignment. Your goal in all three is to extract their perspective, not to change their mind. Walk in trying to change their mind and you look inflexible; walk in trying to learn how to fit their priorities and you look strategic and leave with the information to adapt.

### 5.3 The structured document

His recommendation is to write a structured document first, because writing forces you to think through beliefs and data. He recommends opening with an SCQA paragraph:

| Part | Content |
|---|---|
| **Situation** | The relevant context |
| **Complication** | Why the situation is a problem |
| **Question** | The core question the document answers |
| **Answer** | Your best answer to it |

He cites Barbara Minto's *The Pyramid Principle* for the underlying rule: give the summarising idea before the ideas it summarises. The full pyramid shapes arguments into at most three top-level arguments with up to three sub-arguments each, recursively; he suggests most people start with SCQA and adopt the whole pyramid only if feedback says presentations are hard to follow. He also recommends aligning stakeholders before the meeting (called nemawashi) and sending an early draft to an executive who will attend and asking what to change.

### 5.4 Worked example (illustrative)

*Scenario: you want to pause adding new services for a quarter while you fix on-call load.*

> **Situation.** Over the last two quarters the number of services our teams operate grew faster than the number of engineers on call.
> **Complication.** Pages per on-call shift have risen, and the two incidents last quarter each took longer to resolve because the responder did not own the failing service.
> **Question.** Should we add new services at the planned rate next quarter?
> **Answer.** No. We should spend next quarter consolidating ownership and runbooks for the five noisiest services, then resume at the planned rate with a rule that a new service names an owner and a runbook before launch.

The paragraph is complete on its own. If the meeting only reaches this opening, the key conversation can still happen. Notice it ends with an answer: Larson warns that presenting a question without a proposed answer makes an executive wonder whether they need a more senior leader.

### 5.5 Mistakes he lists

| Mistake | What to do instead |
|---|---|
| **Fighting feedback** | Gather it; offer one or two relevant data points if you must; revisit later |
| **Evading a problem** | Put it on the table; once it is out you can solve it |
| **A question with no answer** | Bring a proposal people can align behind |
| **Academic structure** | Lead with the conclusion |
| **Fixating on your preferred outcome** | Remember missing context, and that almost every decision is revisited |
| **Measuring the meeting by the agenda** | A good meeting is engaged discussion, even if topics are skipped |

---

## 6. Turning This Into Answers

| Question | Staff-level shape of the answer |
|---|---|
| "How did you improve quality across teams?" | Name the measure, the hot spot you fixed first, the one practice you rolled out and how you piloted it, and what you stopped doing because it was not working |
| "Tell me about influencing without authority." | Your sponsor's aim, the context you fed them, the document you wrote, who you aligned beforehand, what changed |
| "Tell me about a disagreement with a senior leader." | Their goal, your data, your single clear statement, the commitment after the decision, and what you watched afterwards |
| "How do you present to executives?" | The purpose of the meeting, the SCQA opening, the pre-alignment, and how you handled feedback live |

Keep your own stories honest: if your quality work was a hot-spot fix, tell it as that. A modest, measured fix is a better story than an inflated program.

---

## 7. Pitfalls

1. **Reaching for process first.** Try to fix the specific problem directly.
2. **Several rollouts at once.** You compete with yourself for attention and cannot tell what worked.
3. **Announcing instead of adopting.** A mandate nobody follows is a failure, not a win.
4. **Blaming engineers for low quality.** It is the normal state; the gap is the work.
5. **Surprising your manager** with news you could have told them first.
6. **Hiding a problem from leadership.** Disclosure is the way to start solving it.
7. **Arguing a decision again after it is made.** Offer your data once; commit; follow up on the specific risk.
8. **Presenting like a school report.** Put the answer first.
9. **Going in to change their mind.** Go in to learn their constraints.
10. **No answer attached to a problem.**

---

## Drills

1. Name the seven approaches to technical quality in order. Why does Larson recommend the lightest first?
2. What is the performance-engineer mindset when applied to a quality problem? Give an example from the lesson.
3. Why limit yourself to one best-practice rollout at a time? What goes wrong if you run several?
4. What are the three leverage points and why does each deserve extra care?
5. Explain "authority is loaned" and what it implies you should do daily.
6. List the three reasons an executive meeting happens and what your goal is in each.
7. Write an SCQA opening paragraph, with invented, labelled-illustrative facts, proposing to delay a feature to fix an operational problem.
8. A senior leader rejects your proposal in a meeting. Describe, step by step, what you do in the meeting, after it, and two weeks later.

---

## Homework

**Part A.** Pick one quality problem you have seen. Do the hot-spot exercise: gather a month of evidence, find where it concentrates, and write the smallest fix. If it concentrates nowhere, say so and ask what that implies.

**Part B.** Write three countable properties that define quality for a codebase you work in, in the spirit of §3.5. For each, say how you would instrument it and what the first number would tell you.

**Part C.** Write the SCQA opening paragraph for a proposal you actually want to make. Send it, before the meeting, to one person who will be in the room and ask what to change. Record what they said.

**Part D.** List the things your manager does not currently know that they would want to know, and set up one routine (a weekly note or a shared thread) to feed it. After two weeks, ask what was useful.

---

## Sources

All read on 2026-11-26. This lesson rests on one author's guides, which are practitioner recommendations rather than research results.

- Will Larson, "Manage technical quality", staffeng.com/guides/manage-technical-quality, read through the quality-program section and the first paragraphs of the closing section; the final paragraphs were not read.
- Will Larson, "Staying aligned with authority", staffeng.com/guides/staying-aligned-with-authority, read in full.
- Will Larson, "Present to executives", staffeng.com/guides/present-to-executives, read in full.
- Dropbox Engineering Career Framework, IC5 Staff Software Engineer page, dropbox.github.io/dbx-career-framework, read 2026-11-26 (communication, decision-making and strategy expectations, used only to show that a published ladder asks for them).

**Not consulted:** *Accelerate*, *The Pyramid Principle*, *A Philosophy of Software Design*, and *Building Evolutionary Architectures*, all cited by Larson. This lesson relays his description of them and does not vouch for them. The staffeng.com guides on creating space for others and building a network of peers were not read.

*Last reviewed: 2026-11-26. This lesson states no compensation figures.*
