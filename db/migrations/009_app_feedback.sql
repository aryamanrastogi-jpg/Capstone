-- 009 - the in-app survey (the Feedback button in the sidebar).
-- Run after 001-008. Idempotent. db/schema.sql and db/policies.sql carry the
-- same definitions for fresh installs.
begin;

-- One row per survey sent. The author is filled in by the database from the
-- signed-in account, so a client cannot file feedback as somebody else, and
-- the row goes when the account does (Profile > Delete account).
create table if not exists public.app_feedback (
    id          uuid primary key default gen_random_uuid(),
    profile_id  text not null default public.app_profile_id()
                references public.profiles (id) on delete cascade,
    role        text check (role in ('student', 'teacher')),
    rating      smallint not null check (rating between 1 and 5),
    suggestion  text check (length(suggestion) <= 1000),
    comments    text check (length(comments) <= 1000),
    created_at  timestamptz not null default now()
);

create index if not exists app_feedback_created_at_idx
    on public.app_feedback (created_at desc);

-- Write-only from the app: a signed-in user may add their own rows and
-- nothing else. No select, update or delete policy exists, so no client role
-- can read feedback back - the team reads it in the Supabase dashboard.
alter table public.app_feedback enable row level security;

revoke all on public.app_feedback from anon, authenticated;
grant insert (role, rating, suggestion, comments) on public.app_feedback to authenticated;

drop policy if exists app_feedback_insert on public.app_feedback;
create policy app_feedback_insert on public.app_feedback
    for insert to authenticated
    with check (profile_id = public.app_profile_id());

commit;

notify pgrst, 'reload schema';
