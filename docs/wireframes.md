# Low-Fidelity Wireframes

These show layout only, not styling. Key: `[Button]`, `[____]` input, `[v]` dropdown. Parts marked "(upcoming)" are being built now. Sidebars are shortened: the full page lists are in `components/navigation.py` (they also include My Class, Practice Generator and Mock Exam).

## 1. Landing / Sign in
```
+------------------------------------------------------------+
| AssessAI                                                   |
|  AI-assisted study support, with teacher oversight         |
|  upload work -> weak topics -> study camp -> improvement   |
+----------------------------+-------------------------------+
|  [Sign in] [Sign up] tabs  |  No account needed            |
|  Name     [____________]   |  [Explore the demo]           |
|  (sign up only)            |                               |
|  Email    [____________]   |                               |
|  Password [____________]   |                               |
|  [Sign in]                 |                               |
+----------------------------+-------------------------------+
```

## 2. Student - My Work
```
+-----------+------------------------------------------------+
| SIDEBAR   | My Work                                        |
| AssessAI  | Question set [v]   Type of work [v homework]   |
| My Work   | Your work [ drop .txt / .pdf ]                 |
| My Quest. | Mark your teacher gave (optional) [__]         |
| Progress  | [Get estimate]                                 |
| StudyCamp |------------------------------------------------|
| Profile   | ESTIMATE 7/10   (not official until reviewed)  |
| [Sign out]| Went well: ...    Mistake types: ...           |
|           | Next steps: ...   [Show me how to approach]    |
|           | Attempts: #1 5/10  #2 7/10  [Compare attempts] |
+-----------+------------------------------------------------+
```

## 3. Student - My Progress
```
+-----------+------------------------------------------------+
| SIDEBAR   | My Progress                                    |
|           | [Average 64%] [Uploads 12] [Priority topics 2] |
|           | Score trend per topic      (line chart)        |
|           | Topic standing: Algebra ...... Priority        |
|           |                 Ratio ........ Secure          |
|           | Repeated mistakes (bar) | By type of work (bar)|
|           | [Download CSV] [Download PDF]   (upcoming)     |
+-----------+------------------------------------------------+
```

## 4. Student - Study Camp
```
+-----------+------------------------------------------------+
| SIDEBAR   | Study Camp                                     |
|           | Length [3 ---o------ 14 days]                  |
|           | Topics [x] Algebra [x] Fractions [ ] Angles    |
|           | [Start camp]                                   |
|           |------------------------------------------------|
|           | Day 3 of 7    Baseline 48%    Latest 61%       |
|           | Today: 5 questions on linear equations         |
|           | Q1 ....   Answer [________________]            |
|           | [Submit session]  [Targeted practice](upcoming)|
+-----------+------------------------------------------------+
```

## 5. Student - Mock Exam (upcoming)
```
+------------------------------------------------------------+
| Mock Exam - Grade 8 Algebra              Time left 24:10   |
| Question 3 of 10                         [4 marks]         |
| Solve 3(x - 2) = 2x + 5                                    |
| [ answer box                                          ]    |
| [< Previous]  [Next >]     Map: 1 2 (3) 4 5 6 7 8 9 10     |
| [Finish exam]  -> score compared with Study Camp baseline  |
+------------------------------------------------------------+
```

## 6. Teacher - Class Overview
```
+-----------+------------------------------------------------+
| SIDEBAR   | Class Overview           Join code: ABC123     |
| Overview  | [Students 24] [Average 67%] [Awaiting review 9]|
| Create    | Student | Avg | Weakest topic | Last active    |
| Upload    | S-01    | 72% | Fractions     | 2 days ago     |
| Review    | S-02    | 58% | Negative nos. | today          |
| Analytics | Mark mismatch (gap > 15 pts)                   |
| Profile   |   S-07  Homework 3   AI 80%  Teacher 55%      |
+-----------+------------------------------------------------+
```

## 7. Teacher - Create Assessment
```
+-----------+------------------------------------------------+
| SIDEBAR   | Create Assessment                              |
|           | Title [__________]  Type [v mock exam]         |
|           | Question 1   Topic [v]   Marks [_]             |
|           |   Question text    [______________________]    |
|           |   Model answer     [______________________]    |
|           |   Marking criteria [______________________]    |
|           | [+ Add question]                               |
|           | Total marks: 20            [Save assessment]   |
+-----------+------------------------------------------------+
```

## 8. Teacher - Review Grading
```
+-----------+------------------------------------------------+
| SIDEBAR   | Review Grading      Show [v awaiting review]   |
|           | S-03 - Grade 8 Algebra                         |
|           | Q1  Student answer ......  AI 2/3 "sign error" |
|           |     Model answer (teacher only) ......         |
|           |     Score [2]   Feedback [______________]      |
|           | [Accept]  [Save edit]  [Flag]                  |
|           | Q2  ...                                        |
+-----------+------------------------------------------------+
```

## 9. Teacher - Class Analytics
```
+-----------+------------------------------------------------+
| SIDEBAR   | Class Analytics        Assessment [v]          |
|           | Score distribution         (histogram)         |
|           | Hardest questions (bar) | Error categories     |
|           | Revision priorities: 1. Negative numbers ...   |
|           | AI accepted unedited: 64%                      |
|           | [Download CSV] [Download PDF]   (upcoming)     |
+-----------+------------------------------------------------+
```

## 10. Profile
```
+-----------+------------------------------------------------+
| SIDEBAR   | Profile                                        |
|           | (avatar)   [Upload photo]                      |
|           | Name  [__________]    Email (read only)        |
|           | Role: student                                  |
|           | [Save changes]                                 |
|           | Privacy controls (upcoming)                    |
+-----------+------------------------------------------------+
```
