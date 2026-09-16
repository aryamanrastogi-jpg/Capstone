# Sample Assessment Materials

Three synthetic Grade 7-9 maths assessments with student responses, for demos, user testing and grading evaluation. **Everything here is made up.** No real students, schools or names. Student IDs such as `S-102` are placeholders.

## Files

| Assessment | Grade / type | Questions | Marks | Responses |
|---|---|---|---|---|
| `assessment_01_grade7_fractions.md` | Grade 7, homework | 5 | 12 | `assessment_01_response_A/B/C.txt` |
| `assessment_02_grade8_linear_equations.md` | Grade 8, exercise | 6 | 15 | `assessment_02_response_A/B/C.txt` |
| `assessment_03_grade9_mock_exam.md` | Grade 9, mock exam | 6 | 18 | `assessment_03_response_A/B/C.txt` |

Also:

- `teacher_marks.csv` - per-question reference marks for all 9 responses above, with a note on each mistake.
- `demo_linear_equations_hw3_response.txt` - matches **Linear Equations - Homework 3**, the set already built into demo mode (`data/sample_data.py`), so it can be uploaded with no set-up. Q1 fully correct (3/3); Q2 forms the equation but subtracts 6 instead of adding it (teacher reading: 1/4). Use it for live demos and student test sessions.

Each assessment file has, per question: the question, the marks, the topic, a model answer and marking criteria (one line per mark).

## Response quality

| Response | Assessment 1 (/12) | Assessment 2 (/15) | Assessment 3 (/18) | Style |
|---|---|---|---|---|
| A | 12 | 15 | 18 | Strong, full working, `Question N` markers |
| B | 4 | 1 | 5 | Weak, typical misconceptions, `Question N` markers |
| C | 7 | 10 | 13 | Mixed: right method, slips, `N.` markers |

Typical mistakes included: adding numerators and denominators, "bigger denominator means bigger fraction", decimal-to-percentage slips, sign errors when expanding brackets, only multiplying the first term in a bracket, `-3^2 = -9`, perimeter using two sides, forgetting the square root in Pythagoras, tan instead of sin, diameter used as radius, "percentage up then down cancels out", open vs filled circle on inequalities.

The teacher marks are one reasonable reading of the criteria. Where a call is borderline (for example implied working in assessment 2, response C, question 2) the note says so. Treat them as the reference for agreement checks, not as absolute truth.

## Using them in the app

1. **Create the assessment.** Sign in as a teacher (or use the demo as a teacher), open **Create Assessment**, and copy in each question's text, marks, model answer and marking criteria from the `.md` file. Keep the questions in the same order.
2. **Upload a response.** On **Upload Responses** (teacher) or **My Work** (student), upload one of the `.txt` files. Every response file uses `Question 1` or `1.` markers, so the answer splitter (`services/answer_splitter.py`) cuts it into one answer per question. All 9 files split confidently; the `Student:` / `Assessment:` header lines are ignored as text before the first marker.
3. **Review.** Open **Review Grading** and compare the AI recommendation with `teacher_marks.csv`.

## Using them for evaluation

`teacher_marks.csv` has one row per response per question (`response_file, assessment, question, max_marks, teacher_mark, note`). Use it to work out the success metrics in `docs/success-metrics.md`: % of questions within 0.5 marks of the teacher and mean absolute error. The grading evaluation script `scripts/evaluate_grading.py` reads its own labelled dataset (`data/grading_eval.json`) by default and takes a `--dataset` option. `teacher_marks.csv` is not in that format, so convert it before pointing the script at these files, or work out the two figures from a spreadsheet.

## Adding more samples

- Keep names synthetic (`S-4xx`) and never paste real student work here.
- Start each answer with `Question N` or `N.` at the start of a line, in order.
- Add a row per question to `teacher_marks.csv`.
