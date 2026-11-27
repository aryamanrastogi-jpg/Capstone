-- 013 - several named classes per teacher, schools, and a student's view of
--       their class
--
-- WHAT CHANGES
--   * classes: a teacher can run more than one class (Year 9 Maths, Year 10
--     Maths), each with its own name and its own join code. class_invites gets
--     class_id, so a code now leads into one class, not just to a teacher.
--   * profiles.class_id: the class a student sits in. profiles.teacher_id stays
--     exactly as it was - every policy since 003 reads it - and the functions
--     below always set the two together. A teacher sits in no class.
--   * profiles.school: free text, from the sign-up metadata (like the name, see
--     004), from Profile, or from the admin for a new teacher. Its owner may
--     change it, like the name and year group. Sign-up also takes a year group.
--   * my_class(): the signed-in student's class name, teacher's name and
--     teacher's school. A student cannot read their teacher's profile row
--     (profiles_select_self in db/policies.sql), so until now the app could
--     only say "your teacher".
--   * list_schools(): the schools that have a teacher on the app, for the
--     sign-up suggestions and the public Schools page. Names only, callable
--     signed in or not. Students' own entries are not listed: anything typed
--     into a public sign-up box can be junk.
--   * Every function that moves a student or promotes a user now sets or clears
--     class_id as well: join_class (008's rate limit kept), leave_class,
--     remove_from_roster, redeem_teacher_invite, admin_make_teacher,
--     admin_demote_teacher. admin_list_teachers also returns the school.
--
-- EXISTING DATA
--   Every teacher who already has a class code or students gets one class
--   called "My class"; their codes and students move into it, so a code handed
--   out before this keeps working.
--
-- WHILE THE OLD APP IS STILL RUNNING
--   rotate_class_code() with no argument - what the app before this calls -
--   still works: it issues a code for the teacher's first class, making
--   "My class" if they have none. The new app calls rotate_class_code(p_class_id).
--
-- Run after 012_admin_create_teacher.sql and BEFORE deploying the app code that
-- uses it. Safe to re-run. One transaction: if any statement fails, nothing
-- here is applied.

begin;

-- ---------------------------------------------------------------------------
-- classes
-- ---------------------------------------------------------------------------
create table if not exists public.classes (
    id          text primary key
                default ('cls_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 12)),
    teacher_id  text not null references public.profiles (id) on delete cascade,
    name        text not null check (length(trim(name)) between 1 and 60),
    created_at  timestamptz not null default now()
);

create index if not exists classes_teacher_idx on public.classes (teacher_id);

alter table public.classes enable row level security;

-- A teacher sees and manages their own classes. There is no policy for anybody
-- else, so for a student this table does not exist: my_class() below is how a
-- student learns the name of theirs.
drop policy if exists classes_own on public.classes;
create policy classes_own on public.classes
    for all to authenticated
    using (teacher_id = public.app_profile_id() and public.app_is_teacher())
    with check (teacher_id = public.app_profile_id() and public.app_is_teacher());

-- Only the name can be changed after the fact, and a new row can only say whose
-- class it is and what it is called; the id and the date are the database's.
revoke all on public.classes from public, anon, authenticated;
grant select, delete on public.classes to authenticated;
grant insert (teacher_id, name) on public.classes to authenticated;
grant update (name) on public.classes to authenticated;

-- A code belongs to one class. Deleting a class deletes its codes.
alter table public.class_invites
    add column if not exists class_id text references public.classes (id) on delete cascade;
create index if not exists class_invites_class_idx
    on public.class_invites (class_id, revoked);

-- ---------------------------------------------------------------------------
-- profiles: class_id and school
-- ---------------------------------------------------------------------------
-- Deleting a class leaves anyone still in it on the teacher's roster, in no
-- class (the app only offers to delete an empty one).
alter table public.profiles
    add column if not exists class_id text references public.classes (id) on delete set null;
alter table public.profiles add column if not exists school text;
create index if not exists profiles_class_id_idx on public.profiles (class_id);

do $do$
begin
    if not exists (select 1 from pg_constraint
                    where conname = 'profiles_school_length'
                      and conrelid = 'public.profiles'::regclass) then
        alter table public.profiles add constraint profiles_school_length
            check (school is null or length(trim(school)) between 1 and 80);
    end if;
    -- Like teacher_has_no_roster (schema.sql): a teacher sits in no class.
    if not exists (select 1 from pg_constraint
                    where conname = 'teacher_has_no_class'
                      and conrelid = 'public.profiles'::regclass) then
        alter table public.profiles add constraint teacher_has_no_class
            check (role = 'student' or class_id is null);
    end if;
end
$do$;

-- The school is its owner's to change, like the name and year group. class_id
-- is not in the grant: only the functions below move a student.
grant update (school) on public.profiles to authenticated;

-- ---------------------------------------------------------------------------
-- Existing codes and students move into a "My class" per teacher
-- ---------------------------------------------------------------------------
-- The id is derived from the teacher's, so a re-run finds the same class.
insert into public.classes (id, teacher_id, name)
select 'cls_' || substr(md5(t.id), 1, 12), t.id, 'My class'
  from public.profiles t
 where t.role = 'teacher'
   and not exists (select 1 from public.classes c where c.teacher_id = t.id)
   and (exists (select 1 from public.class_invites i where i.teacher_id = t.id)
        or exists (select 1 from public.profiles s where s.teacher_id = t.id))
on conflict (id) do nothing;

update public.class_invites i
   set class_id = 'cls_' || substr(md5(i.teacher_id), 1, 12)
 where i.class_id is null
   and exists (select 1 from public.classes c
                where c.id = 'cls_' || substr(md5(i.teacher_id), 1, 12));

update public.profiles s
   set class_id = 'cls_' || substr(md5(s.teacher_id), 1, 12)
 where s.role = 'student'
   and s.teacher_id is not null
   and s.class_id is null
   and exists (select 1 from public.classes c
                where c.id = 'cls_' || substr(md5(s.teacher_id), 1, 12));

-- ---------------------------------------------------------------------------
-- Sign-up: name (since 004), and now school and year group, from the metadata
-- ---------------------------------------------------------------------------
-- The role is still never taken from the client: always 'student'.
create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
declare
    new_profile_id text := 'usr_' || substr(replace(new.id::text, '-', ''), 1, 12);
    anonymous_code text := 'S-' || lpad(
        (abs(hashtext(new.id::text)) % 9000 + 1000)::text, 4, '0');
    given_name   text := left(trim(coalesce(new.raw_user_meta_data ->> 'full_name', '')), 60);
    given_school text := trim(left(regexp_replace(
        trim(coalesce(new.raw_user_meta_data ->> 'school', '')), '\s+', ' ', 'g'), 80));
    given_year   text := trim(coalesce(new.raw_user_meta_data ->> 'year_group', ''));
begin
    insert into public.profiles (id, auth_user_id, display_name, role, school, year_group)
    values (
        new_profile_id,
        new.id,
        case when given_name = '' then anonymous_code else given_name end,
        'student',
        nullif(given_school, ''),
        case when given_year ~ '^(7|8|9|10|11)$' then given_year::integer end
    )
    on conflict (auth_user_id) do nothing;

    return new;
end;
$fn$;

-- ---------------------------------------------------------------------------
-- Issuing a code, now for one class
-- ---------------------------------------------------------------------------
create or replace function public.rotate_class_code(p_class_id text)
returns text
language plpgsql
security definer
set search_path = public
as $fn$
declare
    me       text := public.app_profile_id();
    new_code text;
begin
    if me is null or not public.app_is_teacher() then
        raise exception 'Only a teacher can issue a class code.';
    end if;
    if not exists (select 1 from public.classes c
                    where c.id = p_class_id and c.teacher_id = me) then
        raise exception 'That class is not yours.';
    end if;

    -- Revoking is the point: a code that leaked must stop working.
    update public.class_invites
       set revoked = true
     where class_id = p_class_id and not revoked;

    new_code := public.generate_class_code();
    insert into public.class_invites (code, teacher_id, class_id)
    values (new_code, me, p_class_id);
    return new_code;
end;
$fn$;

-- The no-argument form the app called before this migration: the teacher's
-- first class, made as "My class" if they have none.
create or replace function public.rotate_class_code()
returns text
language plpgsql
security definer
set search_path = public
as $fn$
declare
    me          text := public.app_profile_id();
    first_class text;
begin
    if me is null or not public.app_is_teacher() then
        raise exception 'Only a teacher can issue a class code.';
    end if;

    select c.id into first_class
      from public.classes c
     where c.teacher_id = me
     order by c.created_at, c.id
     limit 1;

    if first_class is null then
        first_class := 'cls_' || substr(md5(me), 1, 12);
        insert into public.classes (id, teacher_id, name)
        values (first_class, me, 'My class')
        on conflict (id) do nothing;
    end if;

    return public.rotate_class_code(first_class);
end;
$fn$;

-- ---------------------------------------------------------------------------
-- Joining, leaving, removing: class_id moves with teacher_id
-- ---------------------------------------------------------------------------
-- 008's version with class_id added. Its window is kept: at most 10 tries per
-- account per 15 minutes, and the same null for a throttled and an invalid
-- code, so this cannot become a class-code oracle.
create or replace function public.join_class(p_code text)
returns text
language plpgsql
security definer
set search_path = public
as $fn$
declare
    me            text := public.app_profile_id();
    my_role       text;
    found_teacher text;
    found_class   text;
    attempt_count integer;
begin
    if me is null or auth.uid() is null then
        raise exception 'Not signed in.';
    end if;
    insert into public.class_join_attempt_windows(auth_user_id, window_started_at, attempts)
    values (auth.uid(), now(), 1)
    on conflict (auth_user_id) do update
       set window_started_at = case
               when public.class_join_attempt_windows.window_started_at < now() - interval '15 minutes'
               then now() else public.class_join_attempt_windows.window_started_at end,
           attempts = case
               when public.class_join_attempt_windows.window_started_at < now() - interval '15 minutes'
               then 1 else public.class_join_attempt_windows.attempts + 1 end
    returning attempts into attempt_count;
    if attempt_count > 10 then
        return null;
    end if;
    select role into my_role from public.profiles where id = me;
    if my_role <> 'student' then
        raise exception 'Only a student can join a class.';
    end if;
    select i.teacher_id, i.class_id into found_teacher, found_class
      from public.class_invites i
     where i.code = upper(trim(p_code)) and not i.revoked;
    if found_teacher is null then
        return null;
    end if;
    update public.profiles
       set teacher_id = found_teacher, class_id = found_class
     where id = me;
    return found_teacher;
end;
$fn$;

create or replace function public.leave_class()
returns void
language plpgsql
security definer
set search_path = public
as $fn$
declare
    me text := public.app_profile_id();
begin
    if me is null then
        raise exception 'Not signed in.';
    end if;
    update public.profiles set teacher_id = null, class_id = null where id = me;
end;
$fn$;

create or replace function public.remove_from_roster(p_student_id text)
returns boolean
language plpgsql
security definer
set search_path = public
as $fn$
declare
    me text := public.app_profile_id();
begin
    if me is null or not public.app_is_teacher() then
        raise exception 'Only a teacher can change a roster.';
    end if;

    update public.profiles
       set teacher_id = null, class_id = null
     where id = p_student_id and teacher_id = me;

    return found;
end;
$fn$;

-- ---------------------------------------------------------------------------
-- What a student may know about their class
-- ---------------------------------------------------------------------------
create or replace function public.my_class()
returns table (class_id text, class_name text, teacher_name text, teacher_school text)
language sql
stable
security definer
set search_path = public
as $fn$
    select c.id, c.name, t.display_name, t.school
      from public.profiles me
      join public.profiles t on t.id = me.teacher_id
      left join public.classes c on c.id = me.class_id
     where me.auth_user_id = auth.uid();
$fn$;

-- ---------------------------------------------------------------------------
-- Schools on the app: teachers' schools, names only
-- ---------------------------------------------------------------------------
create or replace function public.list_schools()
returns table (school text)
language sql
stable
security definer
set search_path = public
as $fn$
    select min(trim(p.school))
      from public.profiles p
     where p.role = 'teacher'
       and p.school is not null
       and length(trim(p.school)) > 0
     group by lower(trim(p.school))
     order by 1;
$fn$;

-- ---------------------------------------------------------------------------
-- Becoming a teacher clears the class as well as the roster
-- ---------------------------------------------------------------------------
-- 005's function, with class_id cleared next to teacher_id: a teacher sits in
-- no class (teacher_has_no_class above).
create or replace function public.redeem_teacher_invite(code text)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $fn$
declare
    me        text := public.app_profile_id();
    hashed    text;
    invite_id bigint;
begin
    if me is null then
        raise exception 'Not signed in.';
    end if;

    -- Normalise the way people type: stray spaces and lower case are forgiven.
    hashed := encode(
        digest(upper(regexp_replace(coalesce(code, ''), '\s', '', 'g')), 'sha256'),
        'hex');

    -- `for update` so two people racing for the last use of a code cannot both
    -- get it.
    select id into invite_id
      from public.teacher_invites
     where code_hash = hashed
       and use_count < max_uses
       and expires_at > now()
     for update;

    if invite_id is null then
        -- Identical for unknown, used and expired. Do not split this up.
        raise exception 'That invite code is not valid.';
    end if;

    update public.teacher_invites
       set use_count = use_count + 1,
           last_used_by = me,
           last_used_at = now()
     where id = invite_id;

    update public.profiles
       set role = 'teacher', teacher_id = null, class_id = null
     where id = me;
end;
$fn$;

-- 012's function, with class_id cleared too.
create or replace function public.admin_make_teacher(p_auth_user_id uuid)
returns text
language plpgsql
volatile
security definer
set search_path = public
as $fn$
declare
    v_profile_id text;
begin
    perform public.app_require_admin();

    update public.profiles p
       set role = 'teacher', teacher_id = null, class_id = null
     where p.auth_user_id = p_auth_user_id
     returning p.id into v_profile_id;

    if v_profile_id is null then
        raise exception 'No profile for that account.';
    end if;

    return v_profile_id;
end;
$fn$;

-- 011's function: releasing the students clears their class too.
create or replace function public.admin_demote_teacher(
    p_profile_id text,
    p_release_students boolean
)
returns void
language plpgsql
volatile
security definer
set search_path = public
as $fn$
begin
    perform public.app_require_admin();

    if not exists (
        select 1 from public.profiles p
         where p.id = p_profile_id and p.role = 'teacher'
    ) then
        raise exception 'That account is not a teacher.';
    end if;

    if coalesce(p_release_students, false) then
        update public.profiles s
           set teacher_id = null, class_id = null
         where s.teacher_id = p_profile_id;
    end if;

    update public.profiles p
       set role = 'student'
     where p.id = p_profile_id;
end;
$fn$;

-- 011's function plus the school. Its result type changes, so it is dropped
-- and made again (create or replace cannot change a result type).
drop function if exists public.admin_list_teachers();
create function public.admin_list_teachers()
returns table (
    profile_id     text,
    display_name   text,
    student_count  bigint,
    created_at     timestamptz,
    school         text
)
language plpgsql
stable
security definer
set search_path = public
as $fn$
begin
    perform public.app_require_admin();

    return query
        select t.id, t.display_name,
               (select count(*) from public.profiles s
                 where s.teacher_id = t.id and s.role = 'student'),
               t.created_at,
               t.school
          from public.profiles t
         where t.role = 'teacher'
         order by t.display_name;
end;
$fn$;

-- ---------------------------------------------------------------------------
-- Who may call what
-- ---------------------------------------------------------------------------
revoke all on function public.rotate_class_code(text) from public, anon;
grant execute on function public.rotate_class_code(text) to authenticated;
revoke all on function public.rotate_class_code() from public, anon;
grant execute on function public.rotate_class_code() to authenticated;
revoke all on function public.join_class(text) from public, anon;
grant execute on function public.join_class(text) to authenticated;
revoke all on function public.leave_class() from public, anon;
grant execute on function public.leave_class() to authenticated;
revoke all on function public.remove_from_roster(text) from public, anon;
grant execute on function public.remove_from_roster(text) to authenticated;
revoke all on function public.my_class() from public, anon;
grant execute on function public.my_class() to authenticated;
revoke all on function public.redeem_teacher_invite(text) from public, anon;
grant execute on function public.redeem_teacher_invite(text) to authenticated;
-- Anyone may see which schools are on the app, signed in or not.
revoke all on function public.list_schools() from public;
grant execute on function public.list_schools() to anon, authenticated;
-- Trigger handlers and the admin functions stay out of every client's reach.
revoke all on function public.handle_new_auth_user() from public, anon, authenticated;
revoke all on function public.admin_make_teacher(uuid) from public, anon, authenticated;
grant execute on function public.admin_make_teacher(uuid) to service_role;
revoke all on function public.admin_demote_teacher(text, boolean) from public, anon, authenticated;
grant execute on function public.admin_demote_teacher(text, boolean) to service_role;
revoke all on function public.admin_list_teachers() from public, anon, authenticated;
grant execute on function public.admin_list_teachers() to service_role;

commit;

notify pgrst, 'reload schema';

-- ===========================================================================
-- CHECKS - run by hand after applying
-- ===========================================================================
--
-- Every teacher with codes or students has a class, and nobody was left out:
--
--     select count(*) as students_without_a_class
--       from public.profiles
--      where role = 'student' and teacher_id is not null and class_id is null;
--
-- Expected: 0, unless a student's teacher has since lost the teacher role.
--
-- The new functions are closed to signed-out visitors, except list_schools:
--
--     select p.proname,
--            has_function_privilege('anon', p.oid, 'execute') as anon,
--            has_function_privilege('authenticated', p.oid, 'execute') as authenticated
--       from pg_proc p join pg_namespace n on n.oid = p.pronamespace
--      where n.nspname = 'public'
--        and p.proname in ('my_class', 'list_schools', 'rotate_class_code', 'join_class');
--
-- Expected: anon true only for list_schools; authenticated true for all four.
