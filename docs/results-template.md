# Final Results

Fill this in as results come in. Every number needs a date and the commit it was measured on (`git rev-parse --short HEAD`). Metric definitions and targets are in `docs/success-metrics.md`.

## 1. Success metrics

| # | Metric | Target | Result | Met? | Date | Commit | Notes |
|---|---|---|---|---|---|---|---|
| M1 | Questions within 0.5 marks of teacher | >= 80% | | | | | Grader used: rule-based / AI |
| M2 | Mean absolute error per question | <= 0.75 marks | | | | | |
| M3 | AI recommendations accepted unedited / flagged | >= 60% / <= 10% | | | | | n = ___ recommendations |
| M4 | Time saved per assessment | >= 30% | | | | | Hand ___ min/response vs review ___ min/response |
| M5 | Weak-topic improvement (baseline -> mock exam) | +10 pp | | | | | n = ___ students |
| M6 | Task completion without help | >= 85% | | | | | ___ of ___ tasks |
| M7 | Mean SUS score | >= 68 | | | | | Teachers ___, students ___ |
| M8 | Test suite pass rate | 100% | | | | | ___ passed / ___ total |
| M9 | Page load time (median of 3) | < 3 s | | | | | See table 1b |
| M10 | Privacy violations seen | 0 | | | | | |

### 1b. Page load times (deployed app, after wake-up)

| Page | Load 1 (s) | Load 2 (s) | Load 3 (s) | Median (s) |
|---|---|---|---|---|
| Landing | | | | |
| My Work | | | | |
| My Progress | | | | |
| Study Camp | | | | |
| Mock Exam | | | | |
| Class Overview | | | | |
| Review Grading | | | | |
| Class Analytics | | | | |

### 1c. SUS scores

| Participant | Role | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | SUS (0-100) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | teacher | | | | | | | | | | | |
| P1 | student | | | | | | | | | | | |
| **Mean** | | | | | | | | | | | | |

## 2. Grading evaluation

Command run:
```
.venv/Scripts/python scripts/evaluate_grading.py
.venv/Scripts/python scripts/evaluate_grading.py --ai
```

| Run | Date | Commit | Grader path(s) used | Items | Within 0.5 marks | Mean abs. error | Notes |
|---|---|---|---|---|---|---|---|
| Rule-based | | | | | | | |
| AI (`--ai`) | | | | | | | If no provider is configured this falls back to rule-based; say so |

Full output (paste as-is):
```
(paste output here)
```

Worst misses (from `--show-misses`) and why:

| Item | Teacher mark | AI mark | Why it missed | Fix idea |
|---|---|---|---|---|
| | | | | |

## 3. User-testing findings

Sessions: ___ teachers, ___ students, dates ___ to ___. Severity: 1 cosmetic, 2 minor, 3 major, 4 blocker.

### 3a. Task completion

| Task | Participants | Completed alone | With help | Failed | Median time |
|---|---|---|---|---|---|
| T-1 | | | | | |
| S-1 | | | | | |

### 3b. Findings

| ID | Participant(s) | Task | What happened | Severity | Frequency (n of N) | Proposed change | Status |
|---|---|---|---|---|---|---|---|
| F-01 | | | | | | | open / fixed / won't fix |

### 3c. Key quotes

| Participant | Quote | Related finding |
|---|---|---|
| | | |

## 4. Improve the application from feedback

One row per change made because of a finding or a missed metric.

| Finding / metric | Change made | Files changed | Commit | Re-tested? Result |
|---|---|---|---|---|
| F-01 | | | | |
| M1 | | | | |

## 5. Summary

- **Targets met:** ___ of 10
- **Biggest success:**
- **Biggest shortfall and why:**
- **What I would do next:**
