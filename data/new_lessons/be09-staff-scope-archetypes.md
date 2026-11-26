# Lesson 09 — What Staff Engineers Do: Scope and Archetypes

> **Priority:** ★★★☆☆. Matters most if you are interviewing for a Staff-plus role, or if a senior-level story keeps being scored as "strong, but not Staff".
>
> **Study time:** 60 minutes. **Do this after:** Lesson 07 (leveling) and your stories from Lesson 02. This lesson starts where Lesson 07 stops: it assumes you can already tell a senior story, and asks what changes above it.
>
> **Level:** advanced. Optional for a crash plan.

Most engineers hear "Staff" as "Senior, but more". That reading costs candidates the level. A Staff engineer is not a faster Senior engineer; the job changes shape. Coding, relationships and project coordination stay in the week, but they stop being the centre of it. This lesson names what moves to the centre, the four recurring shapes the role takes, and how to tell a story that shows the shape you actually have, with no invented scope.

> **What this lesson will not do.** It does not tell you what any company's Staff rubric says internally; those are not public. It uses one published career framework and one published set of interview-based essays, both named in Sources, and says what each does and does not claim. It states no compensation figures. Every scenario in it is **illustrative**: invented to show a pattern, not a record of any person or company.

---

## 1. Mental Model

> **At Senior you are trusted to own a problem. At Staff you are trusted to decide which problems the organisation should be solving, and to make that decision stick through other people.**

Lesson 07 measured level by the size of the problem and how little you needed from others. Above Senior, two things change at once:

| What changes | At Senior | At Staff-plus |
|---|---|---|
| **Where your work comes from** | Handed to you, or found inside your team's area | Chosen: you pick, edit and sometimes decline problems, for several teams or a whole area |
| **What your output is** | A system or project that works | A direction other people follow, plus the people and decisions that make it durable |
| **How you measure a week** | Things shipped | Decisions changed, people unblocked, problems that stopped recurring |
| **Time to feedback** | Days to weeks | Months to years |
| **Whose interest you serve** | Your team's | The wider organisation's, even when that costs your own team something |

The last row is the one interviewers probe hardest. Dropbox's published framework (read for Lesson 07) says it plainly for its Staff software engineer level: the engineer exercises judgement that favours the priorities of the wider engineering organisation over locally optimal outcomes, and increasingly influences the roadmaps of other teams. A story where you won for your own team and nobody else noticed is a Senior story, however large.

Will Larson's *Staff Engineer* guides make a second point that changes how you read ladders: being Staff is not only a role. It is the intersection of the role, your behaviours, your impact, and your organisation recognising all three. You can act like a Staff engineer without the title, and you can hold the title while doing a different job. Both happen.

---

## 2. Recognise the Shape: Four Archetypes

Company ladders usually define one Staff expectation. In practice the job takes several recurring shapes. Larson's guides name four, drawn from interviews with Staff-plus engineers. The Dropbox framework adopts three of them, says it was heavily inspired by Larson's book, and explicitly says an engineer may be a blend and that the archetype tables are not a checklist.

| Archetype | One-line job | Typical scope | Shape of a good story | Characteristic risk |
|---|---|---|---|---|
| **Tech Lead** | Guides approach and execution for one team, or a small cluster, in close partnership with its manager | A team's roadmap and its hardest technical calls | You scoped something complex, delegated the pieces, unblocked people, and the team's output grew while your own code shrank | Doing the Tech Lead job at Senior impact: coordinating without changing what the team can do |
| **Architect** | Owns direction, quality and approach for a critical technical domain (storage, APIs, a frontend stack) | One domain, across many teams, for years | You held a long-lived technical direction, earned authority through repeated good judgement, and kept close to real users and real code | Designing in isolation; judgement decays the further you drift from real work |
| **Solver** | Goes deep on a knotty problem leadership has marked critical, until it is contained | One problem at a time, wherever it is | A hard, risky, unclear problem; you found a path, the problem became ordinary, and you moved on | Leaving the "solved" problem behind with teams that now must maintain it |
| **Right Hand** | Extends a senior leader's attention, borrowing their authority across a large organisation | A whole organisation, mostly non-purely-technical problems | You walked into a fire, edited the approach, handed execution to the right team, and went to the next fire | Always moving on before you see the result; authority is borrowed, so it requires staying aligned with that leader |

Larson also reports that the archetypes appear at different organisation sizes. Tech Leads exist almost everywhere, and he says an organisation needs roughly one per eight engineers. Architects tend to appear as organisations grow large or carry heavy technical debt. Solvers are common where individuals rather than teams are the unit of planning. Right Hands appear only in organisations of many hundreds or thousands of engineers. Treat these as his observations from his interviews, not as measurements.

> **Why this helps in an interview.** "Tell me about your Staff-level impact" is easy to answer badly by describing a big project. It is easier to answer well once you know which shape you are. A Solver story ends with the problem contained and handed over. A Tech Lead story ends with a team that decides better without you. Mixing the endings makes you sound unsure which job you did.

---

## 3. What Staff Engineers Do All Week

Larson's overview names a small shared foundation under all four archetypes. This section reads each item as an interview signal.

| Activity | What it looks like | What a story about it must contain |
|---|---|---|
| **Setting and editing technical direction** | Helping a group agree where they are trying to get, and a rough path there. It is acceptable that they never fully arrive | The vague shared "we want it better" that you turned into a stated target; who disagreed; what you gave up |
| **Mentorship and sponsorship** | A moderate amount of advice, and considerably more of putting your weight behind other people's growth | A named change in someone's scope or visibility you caused, not "I answered questions" |
| **Injecting engineering context into decisions** | Being pulled into a time-sensitive room (a reorganisation, a roadmap call, a hiring loop for a rare role) and supplying what would otherwise be missing | A decision that changed because of context only you had, and your care to represent engineering, not only your team |
| **Exploration** | Being one of a few trusted people given an ambiguous, important problem and a few months | What you tried, what you ruled out, what you reported, and how you handled the real possibility of failure |
| **Being glue** | The needed but often invisible work that keeps the team shipping (see Tanya Reilly's talk in Sources) | The cost of the work if it had not been done, stated in outcomes. Lesson 12 covers how to frame it |

On writing code: Larson's interview answers, taken together, say most Staff engineers write some, a few write none, none write as much as before, and an occasional all-coding week is normal while frequent ones can signal comfortable rather than important work. He also reports a reason several keep some hands-on work: it keeps their decisions informed by what the rest of the team experiences. Have a one-sentence answer ready for "do you still code?" that names what you wrote recently and why (Lesson 03 already drills the manager version of this question).

**Slow feedback is part of the job.** Larson notes that the timeframes lengthen from days to weeks, months and years, and that ending some days feeling you accomplished nothing is normal. In a story, this shows up as a measure with a long horizon. If every result in your story landed within a sprint, the interviewer may reasonably conclude your scope was a sprint.

---

## 4. Reading a Real Ladder: IC4 to IC5

The Dropbox Engineering Career Framework is public, so we can compare two of its levels directly. This is Dropbox only; do not map the numbers to another company.

| Dimension | IC4 Software Engineer (nearest to Senior) | IC5 Staff Software Engineer |
|---|---|---|
| **Scope** | Owns the team's half-year and yearly goals; defines technical solutions and processes that level up the team | Delivers multi-year, multi-team product or platform goals; defines both the what and the how of open-ended work |
| **Collaborative reach** | A strong team leader whose impact is beginning to extend outside the team | Increasingly influences other teams' roadmaps; favours the wider engineering organisation over a locally best result |
| **Decision making** | Makes independent technical decisions under open-ended requirements and tough prioritisation | Leads decisions in critical situations even when unpopular, seeking diverse views and then disagreeing and committing when needed, rather than waiting for consensus |
| **Strategy** | Plays a key role in medium-to-long-term strategy for business-impacting projects | Defines a long-term strategy for the team that accounts for company priorities, customer needs and technical limits |
| **Talent** | Levels up less-experienced teammates; gives quality feedback on teammates' designs | Coaches teammates toward the next level, spreads knowledge through talks and writing, takes part in hiring for senior candidates |
| **Craft** | Designs coherent multi-component systems and rolls out features reliably, with monitoring in place | Reduces complex designs to simple foundations; reviews cross-team designs; owns the health of a system so it does not depend on the maintainers having the author's expertise |

*Source: Dropbox Engineering Career Framework, IC5 Staff Software Engineer page and the Archetypes Behaviors and Clarifications and Myths pages, read 2026-11-26. The IC4 column is from the IC4 Software Engineer page, also read 2026-11-26. Paraphrased, not quoted.*

Two details in that framework are worth carrying into an interview.

1. **It treats "reaching Staff" as sustained impact, not a project.** Its promotion principles say promotions recognise demonstrated, sustained impact at the next level, that there is no checkbox set that guarantees one, and that it does not promote on hope. If your best story is one big week, it is a weak Staff story.
2. **It says you need not match every behaviour.** The framework states it is not a checklist and that individuals take on different personas. That is permission to be deep in one shape instead of thin across all, which is how to present yourself.

---

## 5. Choosing What to Work On

If the job is choosing problems, then what you decline is part of your story. Larson's "work on what matters" guide gives a vocabulary that works in an interview as well as in a week.

| Trap | What it is | How to recognise it in your own stories |
|---|---|---|
| **Snacking** | Easy, low-impact work that feels productive | The story has many finished items and no hard one |
| **Preening** | Low-impact work that happens to be visible | The result was praised in a meeting but nothing downstream changed |
| **Chasing ghosts** | Importing the last company's problems into this one | You pushed a strategy that, in hindsight, solved a problem you had before you joined |

His positive list, restated as questions to ask of a candidate story:

- Was there an existential risk, and did you engage with it? (If something dire is happening, that is where to be.)
- Was there room and attention? Larson advises being sceptical of piling onto leadership's top priority, where many people already work; the better places matter to the company but still have room to do the work.
- Did you invest in growing people (onboarding, mentoring, coaching), which he calls both underinvested and highly leveraged?
- Did you make a small edit that unblocked a project, or help finish one that could not close itself?
- Did you do something that would not have happened without you?

The last one is the best Staff-story question. "What would not have happened if I had not been here?" has an answer for Staff work and often has none for busy senior work.

---

## 6. Worked Examples (all illustrative)

These are invented. They show how the same facts read differently under different archetypes, and what a missing piece sounds like.

### 6.1 A Tech Lead story, told weakly and then well

*Illustrative scenario: a payments team of eight, one manager.*

**Weak.** "I was the tech lead for the checkout rewrite. I broke it into tasks, assigned them, reviewed all the pull requests, and we shipped on time."

Nothing is wrong, but the interviewer cannot tell what would have happened without you, and your review of every pull request suggests the team could not decide without you.

**Better.** "The team kept missing estimates because every cross-service change waited on one reviewer: me. I wrote down the three decisions that were actually blocking people, made two of them with the team in a single meeting, and wrote a short guide for the third. I stopped reviewing most pull requests after that and moved to reviewing only interface changes. The measure I watched was how many changes waited more than a day for review, which fell over the next quarter. What I would change: I should have asked the engineers what they were blocked on before assuming it was approvals."

What improved: the problem was found rather than assigned; there is a decision and its reason; the team gets stronger while the lead's own throughput on one task falls; there is a measure with a horizon; there is an unprompted mistake. (Labelled as illustrative: use a real number from your own work if it exists, and say so if it does not.)

### 6.2 A Solver story

*Illustrative scenario: a nightly job that occasionally corrupts a downstream report.*

The skeleton: leadership flagged it as a risk to a launch; no team could reproduce it; you were given a few weeks and no new staff. You describe the hypotheses you ruled out in order, the experiment that separated two of them, the fix, and the check that proved it. Then the part that separates a Staff Solver from a clever debugger: you wrote up the failure mode and handed the area to the owning team with a test and an alert, so it did not become theirs to rediscover. Larson notes the risk of leaving the teams that maintain a "solved" problem annoyed; naming the handover shows you saw it.

### 6.3 What a missing piece sounds like

| The interviewer hears | The likely gap | The fix, if the fact is true |
|---|---|---|
| "…and then the team adopted it." | You do not say how | One sentence on who objected and what you changed to win them over |
| A large project, no decision | Scope without judgement | Name the choice between two real options and why you picked one |
| "I was the only one who could do it." | A Solver story with no handover | Add what you did so someone else can maintain it |
| Every result lands within one release | Senior altitude | Add the longer-horizon measure, even if it is still maturing |

---

## 7. Pitfalls

1. **"Staff is Senior with a bigger project."** The job changes: direction and people, not only throughput.
2. **Claiming an archetype you did not live.** A Right Hand story needs borrowed authority from a senior leader; claiming one from a team-level job will not survive a follow-up.
3. **A hero story.** Larson argues you are more likely to change a company's trajectory by growing the people around you than by personal heroics. A story where everything depended on you reads as a risk, not a strength.
4. **Treating mentorship as a ladder checkbox.** Larson says this wastes one of the most valuable activities at the level. Describe a person who changed, not a meeting held.
5. **No loser in the story.** Someone's preferred option was not chosen. Say who, and how you left that relationship.
6. **Local optimisation.** A story that benefits your team at the organisation's cost is exactly what the Dropbox IC5 expectation warns against.
7. **Vision with no specifics.** "I aligned stakeholders around a strategy" gives the interviewer nothing to challenge, which makes it sound hollow. Lesson 10 shows what specific looks like.
8. **Inventing a number.** If you did not measure it, say what you would measure. An invented figure fails the first follow-up.

---

## Drills

1. In two sentences, explain why "a Staff engineer is a faster Senior engineer" is a misleading description. Name two things that move from the centre of the week to the edge.
2. Name Larson's four archetypes and give the typical ending of a good story for each.
3. Why does the Dropbox framework say its archetype tables are not a checklist, and how should that change the way you present yourself?
4. Rewrite this at Staff altitude, keeping the facts invented but plausible and labelled as illustrative: "I was tech lead for the search migration and we finished on time."
5. What is the difference between snacking and preening? Give one example of each from your own week.
6. Name the five shared activities in §3. Pick the one you have least evidence for and say what story you would need to find.
7. An interviewer says: "Your result all landed in one quarter." What does the interviewer suspect about your scope, and what could you add if it is true?
8. Larson notes that Solvers often leave teams maintaining a "solved" problem. What two artefacts would you hand over so the problem does not return?

---

## Homework

**Part A.** Write one sentence for each archetype describing what a typical week would contain. Mark the one that fits your best story. Mark a second if you are a real blend, and say which parts of each.

**Part B.** Take your highest-scoring story from Lesson 07's calibration. Add the three Staff signals this lesson stresses: the decision and its loser, the thing that would not have happened without you, and a measure with a horizon longer than one release. If you cannot add one honestly, write down what is missing rather than inventing it.

**Part C.** List your last six months of work in one column. Next to each item mark S (snack), P (preen), or M (mattered). Find the largest M item and write it as a two-minute story following the "weak to better" example in §6.1. Time it aloud.

**Part D.** Write your "do you still code?" answer in two sentences: what you wrote recently, and why you do or do not keep some hands-on work.

---

## Sources

All pages below were read in full or in the stated part on 2026-11-26. Statements about what an organisation's internal rubric says are limited to the public Dropbox framework.

- Will Larson, *Staff Engineer* guides, staffeng.com/guides: "Staff archetypes", "What do Staff engineers actually do?", "Work on what matters", read in full. Used for: the four archetypes and where they tend to appear; the shared foundation of activities; the observations about writing code and slow feedback; snacking, preening and chasing ghosts. The interview-derived statements (one Tech Lead per eight engineers, the stages at which archetypes appear) are Larson's reports from his own interviews, not measured data.
- Dropbox Engineering Career Framework, dropbox.github.io/dbx-career-framework: IC5 Staff Software Engineer page, "What is Impact?", "Archetypes Behaviors", "Clarifications and Myths", and "Promotion Principles", read in full; the IC4 Software Engineer page was read as well. No page shows a date. The Staff expectations paraphrased in §4 come from these pages.
- Tanya Reilly, "Being Glue" (talk text), noidea.dog/glue, read in part (the opening abstract and the first half of the story). Used only to define glue work.

**Not consulted** (named so you do not assume they were): Larson's guides on interviewing for Staff-plus roles, ladders from other companies, and the full text of *The Staff Engineer's Path* and *Staff Engineer*. The staffeng.com stories pages were not read; only the guides.

*Last reviewed: 2026-11-26. This lesson states no compensation figures.*
