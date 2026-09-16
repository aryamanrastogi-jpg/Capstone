# Project Success Metrics

Each metric has a target and a method. Results go in `docs/results-template.md`.

| # | Metric | Target | How it is measured |
|---|---|---|---|
| M1 | Grading agreement with teacher marks | 80% or more of questions within 0.5 marks of the teacher's mark | Run `scripts/evaluate_grading.py` (being added) over the `data/samples/` responses that have teacher marks. Report the % within 0.5 marks |
| M2 | Mean absolute error per question | 0.75 marks or less | Same run as M1 |
| M3 | Teacher acceptance rate of AI recommendations | 60% or more accepted unedited; 10% or fewer flagged | The "accepted unedited" figure on Class Analytics, or a count of accept / edit / flag actions in Review Grading during user testing |
| M4 | Time saved per assessment | At least 30% less time than marking by hand | In testing, a teacher marks 5 responses by hand (timed), then reviews 5 AI-graded responses in Review Grading (timed). Compare minutes per response |
| M5 | Weak-topic improvement | Average gain of 10 percentage points on the student's priority topics | Study Camp baseline score compared with the mock exam mode score (being added) on the same topics |
| M6 | Task completion in user testing | 85% or more of scripted tasks done without help | Observation sheet in `docs/user-testing-plan.md` |
| M7 | Usability (SUS) | Mean SUS score of 68 or more | SUS questionnaire after each session |
| M8 | Test suite pass rate | 100% on `main` | `.venv/Scripts/python -m pytest`, recording passed/total |
| M9 | Page load time | Under 3 s for the first render of each main page on the deployed app | Browser DevTools (Network tab, "Load") on Streamlit Community Cloud. Take the median of 3 loads after the app has woken up |
| M10 | Privacy rules hold | 0 cases of a student seeing a model answer or another student's work | Scripted checks during user testing, plus the RLS rules in `db/README.md` |

## Rules for measuring

- M1 and M2 use the rule-based fallback grader until an LLM provider is set up. Record which grader produced each number.
- Record the date and commit hash with every measurement so it can be repeated.
- Report a metric that misses its target anyway, with the likely reason and what you changed.
