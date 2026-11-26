# 🎤 Presentation script — Personal Financial Agent (12–15 min, live demo included)

Seven parts. Times are targets; the total is about 14 minutes, which leaves room for a slow AI answer.
**Short version (about 10 min):** cut the demo to 3:30 (skip the Year view and the delete), part 4 to 1:30 (only the agent diagram and the 3 rules), and part 6 to 0:30.
With two presenters: **A** does parts 1, 2, 4 and 7, **B** does parts 3, 5 and 6. With more presenters, split by part.
Practical setup (server, warm-up, plan B): see [DEMO.md](DEMO.md).

| # | Part | Time | Slide |
|---|---|---|---|
| 1 | The problem | 1:00 | "Exchange students find out too late" |
| 2 | Value proposition & hypothesis | 1:30 | Value prop + hypothesis |
| 3 | Live demo | 5:00 | (switch to the app) |
| 4 | How it works & how we built it | 2:30 | Architecture diagram + "How we built it" |
| 5 | Does the AI work? We measured it | 2:30 | Evaluation table |
| 6 | Limits & next steps | 1:00 | Limits / roadmap |
| 7 | Close | 0:30 | Value prop again |

---

## 1. The problem — 1:00 (A)

**Slide:** *"Exchange students find out they overspent at the end of the month — when it's too late."*

> "When you go on exchange, you arrive with a fixed amount of money for one or two semesters. Prices are new, and there are lots of one-off temptations: weekend trips, dinners with new friends. Most budgeting apps only tell you **afterwards** where your money went. Nobody tells you **during** the month that you're drifting, or whether you can afford that weekend in Florence **before** you book it."

## 2. Value proposition & hypothesis — 1:30 (A)

**Slide:** the value proposition, then the hypothesis.

> "Our value proposition: **for exchange students living on a fixed budget, we offer real-time spending control and personalized saving advice, using receipt scanning, auto-categorization, monthly and annual dashboards, and an AI budget coach.**"

> "Following the Theory-Based View we saw in class, we started from a **hypothesis**, not from a technology: *students spend better when they always know where they stand, and can ask 'can I afford this?' before buying, with an answer based on their own numbers.* Then we built the smallest product that can test it, and we **measured** whether the AI part actually delivers."

## 3. Live demo — 5:00 (B)

Open the app on the demo account (`/demo`), on the projector and/or the phone.
The demo story is generated relative to today's date, so read the exact amounts off the screen: the script avoids fixed numbers.
Optional: show the QR code of `…/demo` so the professor can try it on their own phone. Each visitor gets a private sandbox.

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00 | 🏠 Home | Show the ring and the 💡 tip | "Read the ring: what is left and how many days remain. The app compares this month with **my own habits**: restaurants are running ahead, and the tip explains **why** (read the 🔍 line: pricier than usual, or more often)." |
| 0:45 | 🏠 Home | Scroll to the charts | "Where my money goes, and my spending day by day against an ideal pace." |
| 1:15 | 📅 Year | Tap Year, then the red bar (last month) | "History is kept, and months reset on the 1st. Last month went over budget (the red bar): that was a weekend in Rome." |
| 1:45 | 🤖 Coach | Type **"Can I afford a 150 € weekend in Florence?"** | While it thinks: "This is a 3-billion-parameter model running **on this laptop**, with no cloud. It doesn't guess: it calls our Python functions on my data." |
| 2:30 | 🤖 Coach | Point at the chip and the 📌 card | "It chose the `can_afford` tool, in Travel. The 📌 card is **Python's own verdict**, word for word: 'possible but tight'. A badly phrased answer can't mislead the student." |
| 3:00 | 🤖 Coach | Type **"Should I put my rent money in bitcoin?"** | "And it knows its limits: no investment advice, it can't move money." |
| 3:30 | ➕ Add | 📸 Scan a real receipt | While it reads (~15 s): "A vision model reads the receipt, its answer is forced into JSON, and Python checks every field." |
| 4:15 | ➕ Add | Show the pre-filled form, then Save | "Nothing is saved until I confirm: the AI proposes, the human decides." |
| 4:45 | 🏠 Home | Show the new expense, maybe delete one with 🗑 | "Everything updates instantly." |

**If the AI is slow:** keep talking (the lines above are written for the waits), or show the 💡 tip, which is computed in Python with no wait. Other problems: see the plan B in [DEMO.md](DEMO.md).

## 4. How it works & how we built it — 2:30 (A)

**Slide:** architecture diagram, with three boxes in a row.
`Student question → Model (Qwen 3B, local) picks a TOOL → Python computes on the student's data → Model phrases the answer + 📌 exact verdict`

> "A chatbot answers from what it remembers. Our coach is an **agent**: it chooses among 5 tools (budget status, can I afford, month-end forecast, saving tips, recent expenses), Python runs them on the student's real data, and the model only **phrases** the result. This is what we called **context and harness** in class: the value is not in the model, it's in what we put around it."

Three design rules, one sentence each:
1. **The model never computes money.** Every number comes from tested Python functions.
2. **Guard rails in Python.** Python fixes what the model gets wrong predictably (for example, it maps "week-end" or "aperitivo" to the right category), and shows its own verdict next to the AI's words.
3. **The human stays in the loop.** A scanned receipt is only a proposal. The model is also replaceable: one file talks to it, so moving from local Qwen to an online model doesn't touch the rest.

**Slide "How we built it" (30 s):**
- Left side, the architecture in one line: `Phone (HTML/JS, displays only) → secure HTTPS link → FastAPI server on our laptop → Python tools + SQLite (one isolated account per user) → local Qwen via Ollama`
- Right side, the method: `GitHub skeleton (FastAPI + CLAUDE.md rules) → 1 branch per feature → tests first → pull request → review → merge` · 13 pull requests · about 270 automated tests

> "We started from a GitHub skeleton with a project charter, our CLAUDE.md, which sets rules like 'tests first' and 'the model never computes money'. Then we built every feature on its own branch, with its tests written first, and merged it through a pull request only once it worked. `main` was always a working version, which is why we can demo it live today."

## 5. Does the AI work? We measured it — 2:30 (B)

**Slide:** the evaluation table (numbers from `evaluation/results/`).

> "Unit tests prove the **code** works. They don't prove the **AI** works. So we ran an **experiment**, like the ones we studied in class: 30 questions in English, French and Italian, each asked 3 times to the real model. The expected answers are computed by our own functions, and we have a **control group**: the same model with **no tools**, where we paste the data into the prompt."

| | Agent (with tools) | Same model, no tools |
|---|---|---|
| Verdict clearly kept (yes / tight / no) | **61 %** | **16 %** |
| Invented amounts | 1 | 4 (and one answer in Portuguese) |
| Right tool / right category | 100 % / 100 % | — |
| Median answer time | 10 s | 3 s |

> "So the tools are not decoration: they make the answers **four times more reliable**, at the cost of speed."

**Second slide:** *measure → fix → measure again.*

> "The experiment also showed two weaknesses. The model never clearly refused out-of-scope requests, and 10 % of its answers came back in the wrong language. We fixed both, Python now tells the model which language to answer in, and then we measured again: **clear refusals went from 0 % to 75 %**, and **the right language from 90 % to 100 %**. To be honest about the method: the 100 % is optimistic, because the language detector was partly tuned on these same questions."

## 6. Limits & next steps — 1:00 (B)

**Slide:** two columns, "Limits" and "Next".

> "Limits: it's a 3B model, so in French it still sometimes turns 'tight' into 'no', and once it gave an investment tip. That's exactly why the 📌 Python verdict is always shown. Answers take about 10 seconds. And today the app runs on a laptop: private, free, and nothing leaves the device, but the Mac has to be on."

> "Next steps: put the app online with a hosted model (an adapter is ready), let the coach add expenses with a confirmation step, and, most importantly, test our hypothesis with real exchange students: one month with the app, compared with their previous months."

## 7. Close — 0:30 (A)

> "To sum up: exchange students get real-time control and advice based on their own numbers. The AI is useful because we **measured** where it's reliable and **built guard rails** where it isn't. Thank you, and you can try the demo on your phone right now."

---

## Likely questions (short answers)

- **Why not just ChatGPT?** It doesn't know your spending. Our agent answers from your own data with numbers computed in Python, runs locally, and your financial data never leaves the device.
- **Why a small local model?** The course asked us to start with Qwen via Ollama. It's free and private. Its weaknesses are measured, and we compensate with guard rails; the model layer is swappable.
- **How do you know the numbers are right?** The tools are 260+ automated tests written before the code. The AI's answers are checked in our evaluation: numbers are faithful 98 % of the time, and the 📌 card always shows Python's verdict.
- **What did the evaluation NOT measure?** It uses keyword-based scoring (ambiguous answers are flagged for a human), and it checks where the numbers come from, not whether the answer is complete. The questions were written by us, not by real users.
- **How does this relate to the Theory-Based View?** We started from a hypothesis about student behaviour, built the minimum product to test it, and the next step is the real test with students. The AI evaluation is a smaller version of the same logic: hypothesis, experiment, control, result.
- **Privacy and security?** The app is private: you can only get in with a one-time personal link or the demo. Each user only sees their own data, and the server checks this on every request, never trusting the browser. A security review found no vulnerability. Money can never move: no tool can do it.
- **What would it cost to scale?** Today it costs 0 € (local model). Online, a free tier is possible for a demo (we checked hosting and AI APIs). At real scale, the cost per question is the key metric to watch.
- **What was the hardest part?** Making a small model reliable: not the model itself, but the harness around it (tools, guard rails, evaluation).
