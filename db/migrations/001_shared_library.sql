-- 001 - shared question library
--
-- Adds the two columns the shared-library feature needs. If you applied
-- db/schema.sql before those columns were added to it, your database does not
-- have them and `create table if not exists` will never give them to you - the
-- table already exists, so the statement does nothing. Hence this file.
--
-- Safe to re-run, and safe to run on a database that already has the columns.

begin;

alter table public.assessments
    add column if not exists is_shared boolean not null default false;

-- `on delete set null`: deleting an original must never remove the working
-- copies other students took from it.
alter table public.assessments
    add column if not exists copied_from_id text
        references public.assessments (id) on delete set null;

-- The library listing filters on both columns together.
create index if not exists assessments_shared_idx
    on public.assessments (is_shared, student_created);

commit;

-- The matching read rule lives in db/policies.sql (`assessments_select`), which
-- is written with `drop policy if exists` and can simply be re-run.
