# Final Presentation and Demonstration

About 15 minutes: 10 minutes of slides and a 5-minute live demo, then questions. Numbers in brackets like `[M1]` come from `docs/results-template.md`; fill them in before the day.

## Slide outline

### 1. Title
**AssessAI - AI-assisted study support for Grade 7-9 maths, with teacher oversight.** Name, course, date.
*Notes:* One sentence: "AssessAI shows students where they are actually weak across a whole term, and lets teachers check every AI mark before it counts."

### 2. The problem
- A student can ask a chatbot about one question, but not "across five months of homework, what am I bad at?"
- Teachers spend hours marking and have little time to spot patterns.
*Notes:* Keep it concrete: one student, a pile of marked homework, an exam in three weeks.

### 3. Who it is for
- Students (main users): see weak topics, fix them before the exam.
- Teachers: oversight, sign off marks.
*Notes:* Mention the 85% student / 15% teacher split and why teachers still matter: trust.

### 4. The solution in one line
`upload past work -> weakness dashboard -> study camp -> measured improvement`
*Notes:* Two rules the whole design follows: **AI output is a recommendation, never a grade**, and **pointers, not answers**.

### 5. How it works (architecture)
- Streamlit app (`app.py`, `st.navigation`, pages per role).
- Services layer: grading, answer splitting, analytics, study camp, mock exam, practice.
- Supabase: Postgres + Auth + Row Level Security + storage for avatars.
- Grading: rule-based today; AI provider plugs in with rule-based fallback.
*Notes:* Draw one box diagram. Say why demo mode exists: it runs with no database, which made testing and this demo safe.

### 6. Privacy and safety by design
- Students never see model answers: the `student_questions` view has no such column.
- Only a teacher makes a score official (RLS on `grading_results`).
- Nobody can make themselves a teacher: roles come from hashed, expiring invite codes.
- Synthetic data only in testing.
*Notes:* Be honest about the one gap from `db/README.md`: grading against a model answer still runs in the student's session until an Edge Function holds it.

### 7. What I measured
Table of the 10 success metrics with targets.
*Notes:* Explain why "within half a mark of the teacher" was chosen: a teacher disagreeing by less than that is normal marking variation.

### 8. Grading results
- Within 0.5 marks: `[M1]`. Mean absolute error: `[M2]`.
- Where it misses (one or two examples from `--show-misses`).
*Notes:* State which grader produced these numbers. If rule-based, say so plainly.

### 9. User testing
- ___ teachers, ___ students. Task completion `[M6]`, SUS `[M7]`, acceptance rate `[M3]`, time saved `[M4]`.
- Top 3 findings.
*Notes:* Use one short quote. Don't overclaim from small numbers.

### 10. What I changed because of feedback
2-3 rows from the "Improve the application from feedback" log: finding -> change -> commit.
*Notes:* This is the strongest evidence of an iterative process. Show a before/after screenshot for one.

### 11. Limitations and next steps
- Small test group; synthetic data.
- No OCR for handwritten or scanned work.
- Model-answer gap (Edge Function next).
- Weak-topic improvement `[M5]` needs a longer trial.
*Notes:* Pick what you would do with three more months.

### 12. Thank you / questions
Live URL, GitHub repo, contact.
*Notes:* Leave the demo tab open behind this slide in case someone asks to see something again.

---

## 5-minute live demo script (demo mode)

**Before the talk:**
- Open the deployed app and click through once so it is awake (Community Cloud apps sleep).
- In the sidebar, click **Reset demo data** so everything starts clean.
- Have `data/samples/demo_linear_equations_hw3_response.txt` on the desktop. It matches **Linear Equations - Homework 3**, which is already in demo mode.
- Have a local copy running (`.venv/Scripts/streamlit run app.py`) as backup, and screenshots of each step as a last resort.
- Browser zoom 125% so the room can read it.

| Time | Do | Say |
|---|---|---|
| 0:00-0:30 | Landing page. Click **Explore the demo**. | "No account needed. Demo mode runs on sample data only, so nothing here is real student data." |
| 0:30-1:30 | Sidebar **Signed in as** -> pick a student. **My Work**: choose **Linear Equations - Homework 3**, upload `demo_linear_equations_hw3_response.txt`, show the per-question split, get the estimate. | "The file is split per question using the 'Question 1', 'Question 2' the student wrote. This is an estimate, labelled as one. Question 2 has a sign mistake - the feedback names the kind of mistake, not the answer." |
| 1:30-2:15 | **My Progress**. Point at the topic standing and the trend chart. | "This is the question a chatbot can't answer: across all my work, where am I weak? These are my priority topics." |
| 2:15-3:00 | **Study Camp**: start a short camp on the priority topics. Open **Mock Exam** and show the start screen. | "A fixed baseline is saved when the camp starts, so the improvement from baseline to mock exam can't be quietly rewritten." |
| 3:00-4:15 | Sidebar -> switch to a teacher. **Review Grading**: open a response, accept one question, edit one mark, flag one. | "Nothing a student sees as official has passed through here without a teacher. Accept, edit or flag - every action is counted, and that is how I measured acceptance rate." |
| 4:15-4:45 | **Class Analytics**: score distribution, hardest questions, AI accepted-unedited figure. Download the report if it is in the build. | "The teacher gets the class pattern, not just individual marks." |
| 4:45-5:00 | Back to slides. | "That's the full loop: upload, see the weakness, practise, and the teacher stays in charge." |

**If something breaks:**
- Upload fails -> switch to typing the answers in "One block of text", or skip to My Progress, which already has sample data.
- App asleep or network down -> switch to the local copy.
- Both down -> screenshots, and say what would have happened. Don't debug live.
