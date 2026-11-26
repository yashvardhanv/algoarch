# Lesson standard (set by the be07 and ds19 samples, approved by the owner 2026-11-26)

Every rewritten or new lesson is one Markdown file in `data/new_lessons/` and follows this.

## Shape

1. Title line `# Lesson NN — <title>`, then a blockquote with **Priority** (stars), **Study time**, **Do this after**, and **Level** if advanced. Separate the lines with a blank `>` line so they render as separate paragraphs.
2. A short opening (two to four sentences): the problem the lesson solves and why it matters in a loop.
3. `## 1. Mental Model`: one idea in a callout, then what follows from it.
4. A recognition or decision section (a table: "if the prompt says X, reach for Y").
5. The substance: worked explanations, with code where the topic is code, and a small table or diagram description where it helps.
6. A pitfalls checklist (numbered, each one a way learners actually lose points).
7. `## Drills`: 6 to 8 questions that can be answered from the lesson.
8. `## Homework`: concrete tasks in order; name real problems or exercises.
9. `## Sources` (what was read, with the access date) or `## Further reading` (what exists but was not consulted, said plainly).
10. Last line: `*Last reviewed: <date>.*`

## Rules

- **Truth:** state only what you can support. Cite a source only if you read it (the page, with the date). Never invent a number, a quote, or a company's internal rubric. If a figure is illustrative, say so.
- **No compensation figures** (rupee amounts, LPA, lakh, crore) anywhere. `npm run lint:comp` must not list the lesson.
- **Code is tested.** Every fenced code block that is meant to run is extracted and run against brute-force or reference checks in `test/lesson_code/<id>_check.py` (or `.js`) and wired into `test/lesson-code.test.js`. Break the code on purpose to confirm the check can fail.
- **Voice:** direct, second person, no filler, no marketing words. Interview altitude: say what to do and why, not a survey.
- **No visuals required yet.** Where a diagram would help, describe it in one line in the text as `Visual (planned): <what it shows>`; the motion kit is built later.
- **Ids and order never change.** Edit the existing file for an existing id. New lessons get the next free id and are added through the curriculum data, not here.
- **Live database:** after the file is committed, load it with `node tools/content/update-guide.js <id> <file> --was <commit before your edit>`. It refuses if the live guide was edited in the CMS. Never run the full importer against the live `data/`.
