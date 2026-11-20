-- 012 - the Admin page creates teacher accounts directly
--
-- THE PROBLEM THIS SOLVES
--   Until now a teacher signed up as a student and then redeemed an invite
--   code on Profile. The Admin page can now make a teacher account in one step:
--   the app creates the sign-in (email + temporary password) with the
--   service-role key through Supabase Auth's admin API, the usual
--   on_auth_user_created trigger makes the profile as a student, and
--   `admin_make_teacher` below turns that new profile into a teacher. The
--   teacher then signs in on the normal Sign In page.
--
-- THE SHAPE
--   * Like every admin function since 011: executable by `service_role` only,
--     and it opens with `app_require_admin()`.
--   * It takes the auth user id the admin API just returned, never an email,
--     so no email is read from or returned by the database here.
--   * teacher_id is cleared in the same statement as the role change: a
--     teacher on somebody else's roster breaks teacher_has_no_roster.
--   * Invite codes keep working exactly as before.
--
-- Run after 011_admin_passkey.sql. Safe to re-run.

begin;

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
       set role = 'teacher', teacher_id = null
     where p.auth_user_id = p_auth_user_id
     returning p.id into v_profile_id;

    if v_profile_id is null then
        raise exception 'No profile for that account.';
    end if;

    return v_profile_id;
end;
$fn$;

revoke all on function public.admin_make_teacher(uuid) from public, anon, authenticated;
grant execute on function public.admin_make_teacher(uuid) to service_role;

commit;

notify pgrst, 'reload schema';
