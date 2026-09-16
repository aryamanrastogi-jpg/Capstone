# User Testing Plan

Goal: find out whether teachers and students can do the core jobs without help, and whether teachers trust the AI grading enough to use it. Results feed metrics M3, M4, M6, M7 and M10 in `docs/success-metrics.md`.

## 1. Who to recruit

| Group | Number | Criteria | How to find them |
|---|---|---|---|
| Maths teachers | 3-5 | Teach Grade 7-9 maths, mark homework or mocks regularly | Own school maths department, supervisor's contacts |
| Students | 4-6 | Grade 7-9, mixed confidence in maths | Through a teacher or a school club, only with school and parent permission |

- Five users per group find most major usability problems. Do not wait for more.
- Sessions: 30 minutes for students, 40 minutes for teachers. In person or video call with screen share.
- Offer a thank-you that does not depend on their opinions (e.g. a snack or a certificate of participation).

## 2. Consent and privacy

- Get written consent before the session (template below). For students under 18, get **parent/guardian consent and the student's own assent**, and the school's permission.
- Participants use **only synthetic data**: the demo mode and the files in `data/samples/`. Nobody uploads real student work.
- Use test accounts, not personal emails where possible (create them in Supabase **Authentication -> Users** with Auto Confirm). Delete them afterwards.
- Record participants by code only: `T1..T5` for teachers, `P1..P6` for students. Keep the code-to-name list on paper or in one private file, and delete it when the project ends.
- Screen recording only with explicit consent. No faces. Delete recordings after findings are written up.
- Anyone can stop at any time without giving a reason.

**Consent form (short):**
> I agree to take part in testing AssessAI, a student capstone project. I will use made-up data only. My name will not appear in any report; I will be referred to by a code. Notes [and a screen recording, if ticked] will be kept privately and deleted by [date]. I can stop at any time.
> Name / signature / date. [ ] I agree to screen recording. (Under 18: parent/guardian signature too.)

## 3. Session setup

- Deployed app URL (or local `streamlit run app.py`), a fresh browser window.
- The sample files from `data/samples/` downloaded to the desktop.
- For teacher sessions: an account already promoted to teacher, with `assessment_01` (all 5 questions) already created from `data/samples/assessment_01_grade7_fractions.md`, and at least one student test account on the roster. Uploading against a set with fewer questions than the file's markers makes the splitter fall back to whole-text grading, so do not cut questions out.
- For student sessions: demo mode is enough. `demo_linear_equations_hw3_response.txt` matches the built-in "Linear Equations - Homework 3" set.
- Printed observation sheet (section 6), a stopwatch, the SUS form (section 7).
- Intro script: "We are testing the app, not you. Please think aloud: say what you are looking for and what you expect. I can't help during tasks, but I will answer questions at the end."

## 4. Teacher tasks

| # | Task (read aloud) | Success means |
|---|---|---|
| T-1 | "Sign in with the test account you were given." | Reaches Class Overview |
| T-2 | "Create a new assessment using questions 1 and 2 of `assessment_03_grade9_mock_exam.md`: text, marks, model answers and marking criteria." | Assessment saved with a total of 6 marks |
| T-3 | "Upload `assessment_01_response_C.txt` for one of your students, against 'Grade 7 Fractions and Decimals'." | Response saved and graded, answers split into 5 questions |
| T-4 | "Review the AI grading for that response. Accept what you agree with, change what you don't." | Every question accepted, edited or flagged. **Time this task (M4)** |
| T-5 | "Mark `assessment_01_response_B.txt` by hand on paper using the criteria." | Time recorded, for comparison with T-4 (M4) |
| T-6 | "Find which topic your class is weakest in." | Names the topic from Class Analytics or Class Overview |
| T-7 | "Give your students a way to join your class." | Finds and reads out the join code |
| T-8 | "Download a report for this assessment." (if the report download feature is in the build) | Downloads CSV or PDF |

## 5. Student tasks

| # | Task (read aloud) | Success means |
|---|---|---|
| S-1 | "Open the app and try it without making an account, as a student." | Enters demo as a student |
| S-2 | "Upload `demo_linear_equations_hw3_response.txt` as your work for 'Linear Equations - Homework 3' and get feedback." | Sees an estimate and next steps |
| S-3 | "Is that score final? How do you know?" | Says it is an estimate until a teacher reviews it |
| S-4 | "Find the topic you should practise most." | Names a Priority topic from My Progress |
| S-5 | "Start a 5-day study camp on your weakest topics." | Camp created with a baseline |
| S-6 | "Get a hint on how to approach a question without seeing the answer." | Uses "Show me how to approach these" |
| S-7 | "Try a mock exam." (if mock exam mode is in the build) | Starts and finishes a mock exam |
| S-8 | "Change the name on your profile." | Name saved |

Privacy check during student sessions (M10): note if a model answer or another student's work is ever visible. It should never be.

## 6. Observation sheet

One sheet per participant. Copy this table.

Participant: ____  Role: teacher / student  Date: ____  Build/commit: ____  Facilitator: ____

| Task | Completed? (Y / Y with help / N) | Time (mm:ss) | Errors / wrong turns | Quotes (what they said) | Severity of any problem (1-4) |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |
| 6 | | | | | |
| 7 | | | | | |
| 8 | | | | | |

Teacher only - for T-4, count: accepted unedited ___ / edited ___ / flagged ___ (M3).

Severity scale: **1** cosmetic, **2** minor (slows them down), **3** major (needed help or a workaround), **4** blocker (could not finish).

## 7. SUS questionnaire

System Usability Scale (Brooke, 1996). Give it right after the tasks. Score each item 1 (strongly disagree) to 5 (strongly agree).

1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to be able to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I would imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

**Scoring:** for odd items, score - 1. For even items, 5 - score. Add the ten results and multiply by 2.5. Result is 0-100. Average is about 68.

**Extra questions (teachers):**
- Would you trust the AI recommendation enough to use it for real marking? Why / why not?
- What would you need to see before accepting a mark without checking it?

**Extra questions (students):**
- Was it clear which scores were estimates?
- Would you use the study camp before an exam?

## 8. Logging findings

After each session, within 24 hours, add every problem to a findings table in `docs/results-template.md` (section 3):

| ID | Participant(s) | Task | What happened | Severity | Frequency (n of N) | Proposed change |
|---|---|---|---|---|---|---|
| F-01 | T2, T4 | T-4 | Did not notice the Flag button | 3 | 2 of 4 | Move Flag next to Accept |

Rules:
- One row per distinct problem. If a second participant hits it, update the frequency, don't add a row.
- Write what they **did**, not what you think they felt.
- Priority to fix = severity x frequency. Fix severity 4 and 3 first.
- When a finding is fixed, add it to the "Improve the application from feedback" log in `docs/results-template.md` with the commit hash, and re-test the task with at least one new participant if possible.
