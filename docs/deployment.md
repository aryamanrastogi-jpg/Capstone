# Deployment Guide

Two parts: (A) bring the Supabase database up to date, then (B) deploy the app on Streamlit Community Cloud. Do A first, because sign-in only works once the migrations are in.

The app still runs in demo mode with no database at all. You only need part A for real accounts and saved data.

---

## Part A - Apply the Supabase schema and migrations

### A1. Know which case you are in

| Case | What to run |
|---|---|
| **Existing project** (you already ran `schema.sql` and `policies.sql` before) | Skip A2. Run A3, then A4 |
| **Brand-new project** | A2, A3, A4 |

Every file is idempotent (safe to run twice), so if you are not sure, follow the brand-new path.

Open **supabase.com -> your project -> SQL Editor -> New query**. For each file below: open it in your editor, copy **the whole file**, paste it into a new query, click **Run**, and wait for `Success. No rows returned` before moving on. Use a fresh query tab for each file.

### A2. Base schema (brand-new project only)

1. `db/schema.sql` - tables, constraints, indexes, the `max_marks` trigger.

`schema.sql` already includes the columns the migrations add, but run the migrations anyway: they also create the sign-up trigger, the functions, the storage bucket and the invite tables. `db/policies.sql` runs last (A4).

### A3. Migrations, in this order

| Step | File | What it adds |
|---|---|---|
| 1 | `db/migrations/001_shared_library.sql` | `assessments.is_shared`, `assessments.copied_from_id` |
| 2 | `db/migrations/002_auth_profiles.sql` | Trigger `on_auth_user_created`: a profile is made at sign-up, always `role = 'student'` |
| 3 | `db/migrations/003_roster.sql` | `class_invites` table and join-code functions (`join_class`, `rotate_class_code`, ...) |
| 4 | `db/migrations/004_profile_details.sql` | Name at sign-up, `profiles.avatar_url`, `delete_my_account()`, the `avatars` storage bucket and its policies |
| 5 | `db/migrations/005_teacher_invites.sql` | `teacher_invites` table (hashed codes) and `redeem_teacher_invite(code)`. Needs pgcrypto, which the file enables |
| 6 | `db/migrations/006_submission_attempts.sql` | `submissions.attempt_number`, so the attempt loop survives a reload |

### A4. (Re-)run the policies

6. `db/policies.sql` - Row Level Security for every table and the `student_questions` view. Re-running it is how an existing project picks up newer rules (for example the shared-library read rule and the `avatar_url` grant).

### A5. Verify

Run each query in the SQL editor and compare with the expected result.

**Tables and RLS** - expect `profiles, assessments, questions, submissions, submission_answers, grading_results, study_camps, study_sessions, class_invites, teacher_invites`, all with `rowsecurity = true`:
```sql
select tablename, rowsecurity
  from pg_tables
 where schemaname = 'public'
 order by tablename;
```

**Migration columns** - expect 4 rows:
```sql
select table_name, column_name
  from information_schema.columns
 where table_schema = 'public'
   and (table_name, column_name) in (('assessments','is_shared'),
                                     ('assessments','copied_from_id'),
                                     ('profiles','avatar_url'),
                                     ('submissions','attempt_number'));
```

**Sign-up trigger** - expect `on_auth_user_created`:
```sql
select tgname
  from pg_trigger
 where tgrelid = 'auth.users'::regclass and not tgisinternal;
```

**Functions** - expect 7 rows:
```sql
select proname
  from pg_proc
 where pronamespace = 'public'::regnamespace
   and proname in ('handle_new_auth_user','delete_my_account','generate_class_code',
                   'rotate_class_code','join_class','leave_class','redeem_teacher_invite')
 order by proname;
```

**Policies** - check there is a list for each table, plus four `avatars_*` policies on `storage.objects`:
```sql
select schemaname, tablename, policyname
  from pg_policies
 where schemaname in ('public', 'storage')
 order by schemaname, tablename, policyname;
```

### A6. Check the avatars bucket

```sql
select id, public, file_size_limit, allowed_mime_types
  from storage.buckets
 where id = 'avatars';
```
Expect one row: `public = true`, `file_size_limit = 2097152` (2 MB), types `image/png, image/jpeg, image/webp`.

Also check in the dashboard: **Storage -> Buckets** shows `avatars` marked Public. Under **Storage -> Policies** it has `avatars_insert_own`, `avatars_update_own`, `avatars_delete_own`, `avatars_select_own`.

### A7. Make the first teacher

No page in the app turns someone into a teacher. After the teacher has signed up in the app, use either:

- **Invite code (005):** mint a code with the query in the comment block at the bottom of `005_teacher_invites.sql`, copy it (it is shown once), and give it to the teacher privately. They enter it in the teacher invite form on their **Profile** page.
- **By hand:** run the `update public.profiles set role = 'teacher' ...` statement in the comments at the bottom of `002_auth_profiles.sql`, with their email.

### A8. Supabase Auth settings

In **Authentication**:

1. **Sign In / Providers -> Email**: enabled. Keep **Confirm email** on. The app already handles it: after sign-up it says "Check your email to confirm it, then sign in", and signing in before confirming shows "Confirm your email address first".
2. **URL Configuration -> Site URL**: set to your deployed app URL, e.g. `https://<your-app>.streamlit.app`. This is where the confirmation email link sends people. If you leave it as `http://localhost:3000`, confirmation links break for everyone else.
3. **URL Configuration -> Redirect URLs**: add the same `https://<your-app>.streamlit.app` and, for local testing, `http://localhost:8501`.
4. Free Supabase projects send only a few auth emails per hour. For user testing with many sign-ups, either set up custom SMTP (**Authentication -> Emails -> SMTP Settings**) or create test users in **Authentication -> Users -> Add user** with "Auto Confirm User" ticked.

### A9. Find the keys

**Project Settings -> API Keys** (or **Data API**):
- **Project URL** -> `SUPABASE_URL`
- **Publishable key** (`sb_publishable_...`; on older projects the `anon` public key) -> `SUPABASE_PUBLISHABLE_KEY`
- **Secret key** / `service_role` -> **do not copy anywhere in this app.** It bypasses every RLS policy.

---

## Part B - Deploy on Streamlit Community Cloud

### B1. Before you push

1. Run the tests locally: `.venv/Scripts/python -m pytest`. All should pass.
2. Check no secrets are tracked: `git status` must not list `.env` or `.streamlit/secrets.toml`. Both are in `.gitignore`. `.streamlit/secrets.toml.example` is safe to commit (empty values).
3. `requirements.txt` is at the repo root. Community Cloud installs from it.

### B2. Push to GitHub

Push `main` to the GitHub repository (currently `origin` = `github.com/aryamanrastogi-jpg/Capstone`). The repo can be private; Community Cloud asks for access.

### B3. Create the app

1. Go to **share.streamlit.io**, sign in with GitHub.
2. **Create app -> Deploy a public app from GitHub** (or "Yup, I have an app").
3. Repository: `aryamanrastogi-jpg/Capstone`. Branch: `main`. **Main file path: `app.py`**.
4. **App URL**: pick a subdomain, e.g. `assessai-capstone`. This is the URL you put in Supabase Site URL (A8).
5. Open **Advanced settings**:
   - **Python version**: `3.13` (matches the local `.venv`, Python 3.13.5). `3.12` also works if 3.13 is not offered.
   - **Secrets**: paste the block below (template in `.streamlit/secrets.toml.example`).
6. Click **Deploy**. The first build takes a few minutes.

### B4. Secrets

```toml
SUPABASE_URL = "https://<project-ref>.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_..."
LLM_API_KEY = ""
LLM_MODEL = ""
```

- Keys must be at **root level** - no `[supabase]` section header. Community Cloud exposes root-level secrets as environment variables, and `utils/config.py` reads everything with `os.getenv`. Keys inside a `[section]` are not exported as environment variables, so the app would not see them.
- `LLM_API_KEY` / `LLM_MODEL` can stay empty. The AI grading pipeline being added falls back to rule-based grading when no provider is configured.
- **Never** put the Supabase secret / `service_role` key here.
- To change secrets later: app menu (three dots) -> **Settings -> Secrets**. The app restarts on save.

### B5. After the first deploy

1. Copy the real app URL into Supabase **Site URL** and **Redirect URLs** (A8) if it differs.
2. Smoke test on the live URL:
   - Landing page loads; **Explore the demo** works as student and teacher.
   - Sign up with a new email, confirm via the email link, sign in.
   - Profile page: change the name, upload a small PNG avatar.
   - As a teacher (after A7): create an assessment, see the class join code.
   - As a student: join with the code, upload `data/samples/assessment_01_response_C.txt`.
3. Record page load times for `docs/success-metrics.md` (M9).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Build fails installing packages | Python version too new or too old for a package | Advanced settings -> set Python 3.12 or 3.13, then **Reboot app** |
| `ModuleNotFoundError` on start | Package missing from `requirements.txt` | Add it, push; the app redeploys automatically |
| Sign-in says "Supabase is not configured on this instance." | Secrets missing, misspelled, or under a `[section]` | Put `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` at root level, save, reboot |
| `policies.sql` fails: `column "avatar_url" ... does not exist` | Policies run before migration 004 on an older schema | Run `004_profile_details.sql`, then `policies.sql` again |
| `column "is_shared" does not exist` when saving an assessment | Migration 001 not applied | Run `001_shared_library.sql`, then `policies.sql` |
| "Signed in, but this account has no profile." | Trigger from 002/004 missing | Run 002 then 004_profile_details; check the trigger query in A5. Users created before the trigger need a profile added by hand |
| `function extensions.digest does not exist` running 005 | pgcrypto not enabled | 005 enables it; if it still fails, enable **pgcrypto** in **Database -> Extensions**, then re-run 005 |
| `must be owner of table objects` running 004_profile_details | Storage policies cannot be created from SQL on this project | Create the bucket and the four `avatars_*` policies in **Storage -> Policies** in the dashboard, with the same rules as the file, then re-run the rest |
| Avatar upload fails | Bucket missing, file over 2 MB, or not png/jpeg/webp | Run the A6 query; upload a smaller png |
| Confirmation email link opens `localhost` | Site URL not updated | Set Site URL to the `streamlit.app` URL (A8) |
| "Email rate limit exceeded" | Free-tier email limit | Wait an hour, use custom SMTP, or add users with Auto Confirm |
| "Invalid login credentials" | Wrong password, or the user was never created | Check **Authentication -> Users** |
| Student cannot see teacher's assessments | Student not on the teacher's roster | Student joins with the class code, or check `profiles.teacher_id` |
| App is slow to open | Community Cloud sleeps apps that are not used | First load wakes it (up to ~1 min); measure load time after it is awake |
| Uploaded PDF gives no text | Scanned image PDF (no OCR) or over 5 MB | Use a digital PDF or `.txt` under 5 MB (`maxUploadSize` in `.streamlit/config.toml`) |
| Changes pushed but not live | Deploy still running or failed | App menu -> **Manage app** to see logs; **Reboot app** |
