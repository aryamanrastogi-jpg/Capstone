# Streamlit Fundamentals - Study Notes for AssessAI

Short notes on the Streamlit ideas this codebase depends on. Each section points to real files. Exercises are at the end.

## 1. The rerun model

A Streamlit page is a Python script that runs **top to bottom on every interaction**. Clicking a button, typing in a box or uploading a file reruns the whole script. Nothing is remembered between runs unless you store it.

In this repo:
- `app.py` runs on every rerun: it seeds data, checks who is signed in, then builds the navigation and runs the chosen page.
- Because everything reruns, slow work (reading a PDF, grading) should only happen when a button is pressed, not on every render.

Key rule: `if st.button("Go"):` is `True` for **one run only**, the one right after the click.

## 2. `st.session_state`

`st.session_state` is a dictionary that survives reruns for one browser session. It is how the demo mode works without a database.

In this repo:
- The in-memory store holds assessments, submissions, grading results, users and the demo flag in session state (seeded from `data/sample_data.py`).
- `store.enter_demo()` on `pages/landing.py` sets a flag, and `app.py` reads it on the next run to decide what to show.
- Widgets with a `key=` save their value into `st.session_state[key]` automatically.

Common mistakes:
- Setting a widget's session state value after the widget has been drawn in the same run raises an error.
- Forgetting a default: use `st.session_state.setdefault("x", 0)`.

## 3. Multipage apps: `st.navigation` and `st.Page`

`app.py` does not use the old automatic `pages/` sidebar. It builds the page list itself:

```python
st.navigation([st.Page("pages/landing.py", title="Welcome")]).run()
```

- Not signed in and no demo: only the landing page is offered.
- Otherwise `components/navigation.py` (`build_navigation(role, signed_in=...)`) returns a different page list for students and teachers.
- This is **not security by itself**: it hides pages, while real access rules live in the service layer and in Supabase RLS (`db/policies.sql`).

## 4. Forms

Inside `with st.form(...)`, widget changes do **not** rerun the script. Everything is sent together when `st.form_submit_button` is clicked.

In this repo:
- `pages/my_class.py` - the `join_class` form (type a join code, then submit).
- `pages/profile.py` - the `profile_form` (edit name, then "Save changes").

Use a form when several fields belong to one action; it avoids half-finished reruns.

## 5. `st.file_uploader`

Returns `None` or an `UploadedFile` (behaves like a bytes file). Reads happen on every rerun while a file is attached.

In this repo:
- `pages/student_home.py` and `pages/my_questions.py` accept `type=["txt", "pdf"]`.
- `pages/upload_responses.py` lets a teacher upload on a student's behalf.
- `pages/profile.py` uploads an avatar.
- PDFs are read with PyMuPDF (text PDFs only, no OCR). Upload size is capped at 5 MB by `maxUploadSize` in `.streamlit/config.toml`.
- Answers are split into questions using markers such as `1.` or `Question 1` (per-question PDF splitting is being extended).

## 6. Theming and config

`.streamlit/config.toml` holds colours, fonts and radii. The same colours live in `utils/palette.py`; change both together. Secrets/keys are read from environment variables in `utils/config.py` (see `docs/deployment.md`).

## 7. Testing with `AppTest`

`streamlit.testing.v1.AppTest` runs a script without a browser, so you can check that pages render and widgets work.

In this repo, `tests/test_pages_render.py`:
```python
at = AppTest.from_file(APP, default_timeout=90)
at.run()
assert not at.exception
```
You can set `at.session_state[...]` before `run()` to pretend to be a student or teacher, then click with `at.button[0].click().run()` and inspect `at.markdown`, `at.metric`, etc.

Run all tests: `.venv/Scripts/python -m pytest`

## Exercises

1. **Rerun counter.** In a scratch file, show `st.write` of a counter stored in session state and a button that adds 1. Then do it with a normal variable and explain why it stays at 1.
2. **Trace a click.** On `pages/landing.py`, follow what happens after "Explore the demo" is clicked, through `app.py`, to the first student page. Write the steps down.
3. **Form vs no form.** Rewrite a two-field input with and without `st.form`. Note how many reruns each causes (add a `print` at the top).
4. **Uploader.** Build a small page that uploads a `.txt` file from `data/samples/` and counts how many `Question N` / `N.` markers it contains.
5. **Navigation.** Add a temporary page to a local copy of the navigation for teachers only, check a student cannot see it, then remove it.
6. **AppTest.** Write a test that runs the app as a student and asserts no exception and that a page title appears. Run it with pytest.
7. **Explain the limit.** In two sentences, explain why hiding a page in `st.navigation` is not enough to protect model answers, and what in `db/policies.sql` does protect them.
