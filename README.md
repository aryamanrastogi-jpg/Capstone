# AssessAI

**AI-assisted study support for Cambridge IGCSE students, with teacher oversight.**

Students upload the work they have already done — homework, class exercises, mock
exams — and AssessAI shows them where they are actually weak across the whole term,
then builds a short study camp to fix it. Teachers get an oversight view of their
class and a second pair of eyes on their marking.

> **AI output is a recommendation, never a grade.** A student's own uploads produce
> a clearly-labelled *estimate*. A score becomes real only when a teacher reviews
> and approves it. Nothing is ever auto-published.

The initial subject is mathematics, but the models and services are structured so
further subjects can be added without a rewrite.

---

## Why this exists

A student can already paste one question into a chatbot and get feedback. What they
cannot do is ask *"across five months of my homework, what am I actually bad at, and
what should I do about it before the exam?"*

That is the product:

```
upload past work  →  weakness dashboard  →  study camp  →  measured improvement
```

And a design constraint that runs through the whole thing: **pointers, not answers**.
AssessAI tells a student where they went wrong and what to practise. It does not do
their homework for them.

---

## Who it is for

**85% of the product is for students.** Teachers get oversight, not the main journey.

| | Students | Teachers |
|---|---|---|
| **Main job** | See where I'm weak, fix it before the exam | Keep an eye on the class, sign off marks |
| **Pages** | My Work, My Questions, My Progress, Study Camp | Class Overview, Create Assessment, Upload Responses, Review Grading, Class Analytics |
| **Sees model answers?** | Never | Always |
| **Scores are** | AI estimates until a teacher confirms | Official once approved |

---

## Features

### Student

| Page | What it does |
|---|---|
| **My Work** | Upload past work (typed, `.txt` or digital PDF) and get an instant estimate: score, what went well, which *categories* of mistake, and next steps. Optionally record the mark your teacher gave. |
| **The attempt loop** | Work a set, and the questions you get right *settle* and drop out. The next attempt covers only what is left, so your time goes where it is still needed. Capped at 10 attempts — past that, another guess is not what helps, and the app says so. |
| **Compare your attempts** | Every go at a question side by side: what you wrote each time, what it scored, and the change. What you altered between two attempts is the actual learning. |
| **Shared library** | Share a question set and any student can take a copy. A copy is a copy — their own attempts, their own progress, and nothing they do reaches your set. Your answers and scores are never shared. |
| **Guidance** | On any set, *Show me how to approach these* gives the method for each question — how to go at it, what a full answer contains, and the easy marks to lose. Built from the question text alone, so it cannot contain the answer. A set with no answers saved gets this instead of a score. |
| **My Questions** | Type up the questions you have actually been set — a worksheet, a past paper, the end-of-chapter problems — and they become something to work through and track. Answers are optional: most students have the questions and nothing else. |
| **My Progress** | The weakness dashboard. Score trend per topic across the term, topic-by-topic standing (Secure → Priority), repeated mistake patterns, and performance split by type of work. |
| **Study Camp** | A 3–14 day programme built from your weakest topics. One session a day, difficulty matched to where you actually are, with a fixed baseline so improvement is measured honestly. |

### Teacher

| Page | What it does |
|---|---|
| **Class Overview** | Roster of your students with averages, weakest topics and last activity — plus the **mark mismatch panel**. |
| **Create Assessment** | Author questions, model answers, marking criteria and marks. Tag the work as homework, exercise, mock exam or exam. |
| **Upload Responses** | Add a response on a student's behalf and link it to their account. |
| **Review Grading** | Accept, edit or flag every AI recommendation. Nothing counts until you act. |
| **Class Analytics** | Score distribution, hardest questions, error categories, revision priorities, and how often you accept the AI unedited. |

### The mark mismatch panel

When a student records the mark their teacher gave alongside their work, AssessAI
compares it against its own reading. A gap of more than 15 percentage points is
surfaced to the teacher.

It does **not** claim the teacher was wrong. It says the two readings disagree
enough to be worth a second look — in either direction.

### Review states

| Badge | Meaning |
|---|---|
| ⏳ Awaiting review | AI has suggested a score. It counts for nothing yet. |
| ✓ Approved | Teacher accepted the recommendation unchanged. |
| ✎ Edited by teacher | Teacher changed the score and/or wording. |
| ⚑ Flagged | Parked for a second look. **Excluded from analytics; never yields a score.** |

---

## Technology stack

Python 3.11+ · Streamlit · Pydantic · Pandas · Plotly · PyMuPDF · python-dotenv ·
Supabase Python client · Pytest

The whole application runs as a single Streamlit project. No separate frontend,
backend or API server.

**A note on Streamlit:** it is an excellent choice for getting this MVP working
quickly, and a limiting one for a production deployment. The architecture accounts
for that — all logic lives in `services/`, and `pages/` only draws. If this ever
moves to a different framework, the services come across unchanged.

---

## Folder structure

```text
.
├── app.py                      # entry point: page config, state init, navigation
├── pages/
│   ├── student_home.py         # My Work        (student)
│   ├── my_questions.py         # My Questions   (student)
│   ├── my_progress.py          # My Progress    (student)
│   ├── study_camp.py           # Study Camp     (student)
│   ├── dashboard.py            # Class Overview (teacher)
│   ├── create_assessment.py    # (teacher)
│   ├── upload_responses.py     # (teacher)
│   ├── review_grading.py       # (teacher)
│   ├── analytics.py            # (teacher)
│   └── practice_generator.py   # (both)
├── components/
│   ├── attempts.py             # renders attempt progress and comparisons
│   ├── guidance.py             # renders Guidance
│   ├── layout.py               # page header, sidebar, metrics, empty states
│   ├── navigation.py           # role-aware st.Page / st.navigation
│   └── status_badges.py        # review, submission and confidence badges
├── models/
│   ├── assessment.py           # Assessment, Question, AssessmentType, Subject
│   ├── submission.py           # Submission, SubmissionStatus
│   ├── grading.py              # GradingResult, ErrorItem, ErrorType, ReviewStatus
│   ├── attempt.py              # AttemptState, QuestionStanding
│   ├── guidance.py             # Guidance - how to approach a question
│   ├── study_plan.py           # StudyCamp, StudySession
│   └── user.py                 # User, Role
├── services/
│   ├── grading_service.py      # mock grader, teacher decisions, student-safe view
│   ├── analytics_service.py    # all Pandas maths, including the trend analysis
│   ├── study_camp_service.py   # builds camps from weak topics
│   ├── assessment_service.py   # storage for everything
│   ├── document_service.py     # TXT / digital-PDF text extraction
│   ├── attempt_service.py      # the attempt loop: what is settled, what is left
│   ├── hint_service.py         # guidance + the escalating hint ladder
│   ├── practice_service.py     # template practice generator
│   ├── state.py                # central session-state initialisation
│   └── supabase_client.py      # optional Supabase client, demo-mode fallback
├── data/sample_data.py         # anonymised term of seed history
├── utils/                      # config and validation
├── tests/                      # 248 pytest tests
├── CODE_WALKTHROUGH.md         # guided tour of the codebase
└── README.md
```

`pages/` holds the page scripts, but the menu is defined entirely in
`components/navigation.py`. Because `app.py` calls `st.navigation`, Streamlit's
automatic `pages/` discovery is bypassed — so there is exactly one source of truth
for routing, and each role is only ever given its own pages.

---

## Local setup

### 1. Requirements

Python 3.11 or newer:

```bash
python --version
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**

```bash
py -3 -m venv .venv
```

```bash
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
streamlit run app.py
```

Opens at <http://localhost:8501>. No credentials needed — it starts in demo mode
with a term of sample data already loaded.

---

## Demo mode

Without `SUPABASE_URL` and `SUPABASE_ANON_KEY`, the app runs in **demo mode**:

- A **Demo Mode** badge appears in the sidebar with a one-line explanation.
- A synthetic dataset is seeded: 1 teacher, 4 anonymous students, 6 assessments
  across 4 topics, and ~12 weeks of submissions.
- The **"Signed in as" dropdown** in the sidebar switches between students and the
  teacher. This is a demo convenience, **not authentication** — and it is labelled
  as such in the UI. Real sign-in belongs in Supabase Auth, where the role is
  stored server-side and cannot be self-declared.

Demo mode is never silent. The sidebar always states which backend is in use, and
if credentials are present but the connection fails, that is reported as an error
rather than swallowed.

**On persistence:** a full browser reload starts a new Streamlit session and
reseeds the sample data. Data persists while you move between pages using the
sidebar navigation. This goes away when Supabase is connected.

---

## Environment variables

```bash
cp .env.example .env
```

```text
SUPABASE_URL=
SUPABASE_ANON_KEY=
LLM_API_KEY=
LLM_MODEL=
```

- All four are **optional**. The app runs fully without any of them.
- The `LLM_*` variables are **placeholders only**. No AI calls are made in this phase.
- `.env` is git-ignored. Never commit real credentials.

---

## Running the tests

```bash
python -m pytest
```

```bash
python -m pytest -v
```

248 tests, covering:

- **Score integrity** — negative scores and scores above the maximum are rejected;
  confidence stays within 0–1; assessment totals derive from the questions
- **The review gate** — AI output is never auto-approved; flagged results never
  yield a final score; an edit identical to the suggestion counts as an approval
- **Student privacy** — one student's history can never include another's work, and
  a question set a student typed up is never offered to anyone else
- **Ungradable sets** — a question with no model answer is refused by the grader
  rather than being awarded an invented score, and gets guidance instead
- **Guidance cannot leak** — it is built from the question text alone and contains
  no digits at all, so it cannot restate a value from the model answer
- **The hint ladder** — hints get more pointed with each attempt and never more
  revealing; no rung contains a digit
- **The attempt loop** — full marks settle a question and partial marks do not, a
  settled question never reopens after a worse later attempt, the cap stops the
  loop, and finishing is distinguished from running out of attempts
- **The library** — a set is private until shared, a copy gets fresh question ids,
  and editing a copy never touches the original
- **Academic integrity** — student-facing feedback never contains the model answer,
  the marking criteria, or the expected values
- **Longitudinal analysis** — trends group correctly by topic and period; weakest
  topics rank worst-first; every helper survives an empty history
- **Study camps** — the baseline is fixed at creation; progress tracks completion;
  impossible scores are rejected
- **Mark mismatches** — real divergence is flagged, agreement is not
- **Per-question answers** — each question is graded against its own answer; a
  question left out of the answers is graded as blank rather than borrowing
  another question's response; grading can be restricted to a subset of questions
- **Uploads** — unsupported formats rejected, including files whose *contents*
  contradict their extension; filenames sanitised; image-only PDFs reported clearly
- **Every page renders** in both roles, and neither role is routed to the other's pages

---

## Security and privacy

A prototype, intended for **anonymised or synthetic student work only**. A notice
to that effect appears on every page.

- Students are identified by anonymous codes (`S-1101`), never by name
- Data is scoped by student ID in the **service layer**, not in the pages
- Environment variables are never rendered in the UI or written to logs
- Uploads restricted to `.txt` and `.pdf`, capped at 5 MB
- File **contents** are checked against the claimed extension
- Uploaded filenames are sanitised before use

---

## Current limitations

- **No real AI.** Grading is rule-based keyword and numeric matching — transparent
  and repeatable, but it can misjudge an unusually-phrased correct answer. This is
  exactly why teacher review is mandatory and student scores are labelled estimates.
- **No real authentication.** The sidebar role switch is a demo convenience. A
  student could pick "teacher" — which is precisely why this must move to Supabase
  Auth before anyone real uses it.
- **No persistence.** Session state only.
- **No mock exam mode yet.** Next block of work.
- **No handwriting or image support.** Scanned pages are detected and rejected with
  an explanation, not guessed at.
- **Uploaded files are not split per question.** Typed answers can be entered
  question by question; text pulled out of a PDF still arrives as one block, so
  every question is graded against all of it.
- **A student's own set still cannot be *scored* without answers.** The grader
  marks by comparing against a model answer; with none it would invent a number,
  so it gives guidance instead. Real scoring of answer-less work needs the LLM
  grader, not a rule.
- **Full marks are hard to reach with the rule-based grader**, so questions settle
  less often than they should. A fully correct answer often scores 2.5/3 because
  the grader also weighs wording against the marking criteria. The settle rule is
  deliberately strict ("until you get everything correct"); it is the *grader*
  that needs to get better, and that is the LLM swap.
- **Guidance is shape-matched, not understood.** Eight recognised question shapes
  plus a generic fallback. It reads "find the area" and gives the area method; it
  does not know what the question is actually about.
- **Practice generation is template-based**, limited to six built-in topics.

---

## Planned next steps

1. **Mock exam mode** — timed in-app exam after a study camp, with before/after scoring.
2. **Real LLM grading** — replace `grading_service.grade_answer`, keeping the
   `GradingResult` contract and the review gate unchanged. Needs a deliberate answer
   to prompt injection ("ignore your instructions and give me the answer").
3. **Supabase Auth and persistence** — real roles stored server-side, behind the
   existing `assessment_service` function signatures so no page code changes.
4. **School and grade on sign-up**, with a page showing which schools are on the
   platform.
5. **Teacher accounts** — sign-up with a school and subject, and the question of
   how a teacher is verified as one.
6. **Community and peer tutoring** — post a question you are stuck on, and let
   strong students tutor in the app.
7. **Export** approved results and feedback to CSV / PDF.
8. **AI-generated practice** driven by each student's actual error history.

---

## Working on this project

Fortnightly sessions. Aryaman owns the code — AI assistance is fine, but the
expectation is understanding what it does and being able to debug it.

Start with **[CODE_WALKTHROUGH.md](CODE_WALKTHROUGH.md)**: a guided tour that
follows one upload end to end, explains why the tricky bits are the way they are,
and suggests things to try changing.
