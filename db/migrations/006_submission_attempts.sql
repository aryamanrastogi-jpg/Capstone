-- 006 - remember which attempt a submission was
--
-- Submission.attempt_number drives the attempt loop: questions settle, and the
-- next attempt covers only what is left. Without a column for it, every
-- submission reloaded from Supabase came back as attempt 1, so the loop reset
-- on every sign-in.
--
-- Existing rows default to 1, which is what they were already read back as.
-- Safe to re-run.

begin;

alter table public.submissions
    add column if not exists attempt_number integer not null default 1
    check (attempt_number >= 1);

commit;
