# 🎬 Live demo guide

About 6 minutes of demo, plus questions. Everything runs locally on the Mac: no internet is needed during the demo.

> **Value proposition:** For exchange students living on a fixed budget, we offer real-time spending control and personalized saving advice, using receipt scanning, auto-categorization, monthly/annual dashboards and an AI budget coach.

## Checklist

**The day before**
- [ ] `git pull` on `main`, then `python -m pip install -r requirements.txt`, then `python -m pytest` (everything must pass)
- [ ] Ollama installed, with both models: `ollama pull qwen2.5:3b` and `ollama pull qwen3-vl:2b-instruct`
- [ ] Phone charged, with the app on its home screen (Safari → Share → Add to Home Screen)
- [ ] A **real receipt** in your pocket (a coffee or a supermarket ticket), plus a photo of it in your photo library
- [ ] Rehearse the script below once with a timer

**15 minutes before**
1. Plug in the Mac. Open the **Ollama** app.
2. If the room Wi-Fi blocks devices from talking to each other (common in universities), turn on your **iPhone hotspot** and connect the Mac to it.
3. In the project folder:
   ```bash
   source .venv/bin/activate
   python -m backend.demo        # fresh demo data + demo receipt dated today
   python -m backend.warmup      # loads both AI models (~30 s)
   BUDGET_DB=data/demo.db python -m uvicorn backend.main:app --host 0.0.0.0
   ```
4. Find the Mac's address (System Settings → Wi-Fi → Details → IP address) and open `http://<that address>:8000` on the phone.
5. Check: the Home screen shows the 💡 Restaurant tip. Ask the coach one throwaway question.
6. Keep `data/demo-receipt.jpg` open on the Mac (plan B for the scan).

The demo uses `data/demo.db`, so your real data (`data/budget.db`) is never touched. Every demo expense shows a "demo data" tag.

## The script

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00 | — | — | "Exchange students arrive with a fixed budget and find out they overspent at the end of the month, when it's too late. We built a budget coach that works **during** the month." |
| 0:30 | 🏠 Home | Show the ring, then scroll slowly | "157 € left, 6 days to go. The app compares this month with my own habits: restaurants are running ahead, so I get a concrete tip." |
| 1:15 | 🏠 Home | Scroll to the charts | "Where my money goes, and day by day against an ideal pace, where rent counts from day 1." |
| 1:45 | 📅 Year | Tap Year, then tap October | "October went over budget: that was the weekend in Rome. History is kept, while each month resets on the 1st." |
| 2:30 | 🤖 Coach | Type **"Can I afford a 150 € weekend in Florence?"** | While it thinks (~15 s): "This is a small model running **on this laptop**. It doesn't guess: it calls our Python functions on my real data." |
| 3:00 | 🤖 Coach | Point at the chips | "Here you can see it chose the `can_afford` tool, in Travel. The 📌 card is Python's own verdict, word for word, so a badly phrased answer can't mislead the student." |
| 3:45 | ➕ Add | Tap 📸 Scan a receipt → take a photo of the real receipt | While it reads (~15–20 s): "A vision model reads the receipt. Its answer is forced into a JSON format, then Python checks every field." |
| 4:30 | ➕ Add | Show the pre-filled form, fix a field if needed, then Save | "Nothing is saved until I confirm: the AI proposes, the human decides." |
| 5:00 | 🏠 Home | Show the expense in the list | "The budget updates instantly." |
| 5:30 | — | — | "Today it runs on a 3-billion-parameter local model. Switching to the Claude API is one adapter file, without touching the rest." |

## Plan B

| Problem | What to do |
|---|---|
| The phone can't open the app | Present from the Mac browser at `http://127.0.0.1:8000`. Everything works the same. |
| The real receipt is misread | Correct the fields on screen and say "that's exactly why the student confirms". Then scan `data/demo-receipt.jpg` from the photo library, which is known to work. |
| The coach is slow (> 30 s) | Keep talking. If it is really stuck, show the 💡 tip on Home: it is computed in Python, with no AI wait. |
| "The AI coach is offline" | Ollama is closed: open it, run `python -m backend.warmup`, and continue with the rest of the app in the meantime. |
| The coach phrases the verdict badly (e.g. "no" instead of "tight") | Point at the 📌 card: "this is why we show Python's verdict next to the AI's words". It is a strength of the design, not a bug. |

## Likely questions

**Why not just use ChatGPT?**
ChatGPT doesn't know your spending. Our agent answers from your own data, with numbers computed in Python, and it runs locally, so your financial data never leaves your device.

**Why a small local model?**
The course asked us to start locally with Qwen via Ollama. It costs nothing and keeps data private. The model layer (`backend/model_client.py`) is isolated, so the Claude API is a drop-in upgrade.

**What does the AI actually do, and what doesn't it do?**
It understands the question, picks a tool, rephrases the result, and reads receipts. It never computes money, never saves anything without confirmation, and gives no investment advice.

**How do you know it works?**
More than 140 automated tests, written before the code. The AI parts are tested with a fake model, so the tests are reliable and run in under a second. Every feature was also tried with the real models, and the mistakes we found are listed in `NOTES.md`.

**What are the limits?**
On this laptop, answers take about 15 s. The small model sometimes phrases things badly (hence the 📌 card). Receipts were tested on clean tickets, not crumpled ones. There is one budget per category, the same every month. See `NOTES.md`.

**What would you do next?**
Switch to the Claude API for better answers, let the coach add expenses (with confirmation), support multiple currencies (an exchange student's home currency), add savings goals and a CSV export, then test with real exchange students for one month (see the README).
