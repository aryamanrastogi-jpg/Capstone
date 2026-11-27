"""Tests for several named classes per teacher, and schools (migration 013).

WHAT MATTERS HERE
  * A class code now leads into one class: joining sets the class and the
    teacher together, and leaving or being removed clears both.
  * Codes are per class: issuing one for Year 9 does not revoke Year 10's.
  * Old behaviour keeps working: a teacher with no class who issues a code gets
    "My class", exactly what rotate_class_code() with no argument does in SQL.
  * A student learns their class and teacher by name through my_class(), never
    by reading the teacher's profile.
  * Schools are tidied, capped, travel in the sign-up metadata, and only
    teachers' schools are listed publicly.
  * The migration keeps its promises (static checks, like test_admin.py does
    for 011): the join rate limit survives, every promotion clears class_id,
    only list_schools() is open to signed-out visitors, setup_all includes 013.

WHAT THEY DO NOT COVER
  Running 013 against Postgres. The SQL is checked by reading it; the live run
  is the Supabase SQL editor, which applies the file in one transaction.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from models import (
    CLASS_NAME_MAX_CHARS,
    DEFAULT_CLASS_NAME,
    SCHOOL_MAX_CHARS,
    ClassMembership,
    Classroom,
    Role,
    User,
    clean_school,
)
from services import admin_service, auth_service, roster_service, school_service
from services.repository import SessionRepository, SupabaseRepository

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "db" / "migrations" / "013_classes_and_schools.sql"

TEACHER_A = "usr_t_a"
TEACHER_B = "usr_t_b"


# --------------------------------------------------------------------------
# A demo-mode store
# --------------------------------------------------------------------------
class _Store:
    def __init__(self, users: List[User]) -> None:
        self.users = users
        self.classes: List[Classroom] = []


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> _Store:
    fake = _Store(
        [
            User(id=TEACHER_A, display_name="Ms Rao", role=Role.TEACHER,
                 school="Greenfield School"),
            User(id=TEACHER_B, display_name="Mr Diaz", role=Role.TEACHER),
            User(id="usr_s01", display_name="Sam", role=Role.STUDENT, year_group=9),
            User(id="usr_s02", display_name="Ana", role=Role.STUDENT, year_group=10),
        ]
    )
    import services.repository as repository_module

    monkeypatch.setattr(repository_module.store, "get_users", lambda: fake.users)
    monkeypatch.setattr(repository_module.store, "get_classes", lambda: fake.classes)
    repository_module.set_repository(SessionRepository())
    yield fake
    repository_module.set_repository(None)


def _user(store: _Store, user_id: str) -> User:
    return next(u for u in store.users if u.id == user_id)


def _class(store: _Store, name: str) -> Classroom:
    return next(c for c in store.classes if c.name == name)


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------
def test_a_school_is_tidied_and_blank_means_none() -> None:
    assert clean_school("  Greenfield   School ") == "Greenfield School"
    assert clean_school("   ") is None
    assert clean_school(None) is None
    assert User(display_name="Sam", school=" Hill  High ").school == "Hill High"


def test_a_class_name_is_tidied_and_cannot_be_blank() -> None:
    assert Classroom(teacher_id=TEACHER_A, name="  Year 9   Maths ").name == "Year 9 Maths"
    with pytest.raises(ValueError):
        Classroom(teacher_id=TEACHER_A, name="   ")


def test_the_admin_page_and_the_model_agree_on_the_school_limit() -> None:
    assert admin_service.SCHOOL_MAX_CHARS == SCHOOL_MAX_CHARS == 80


# --------------------------------------------------------------------------
# Classes
# --------------------------------------------------------------------------
def test_a_teacher_adds_classes_and_each_starts_without_a_code(store: _Store) -> None:
    assert roster_service.create_class(TEACHER_A, "Year 9 Maths").ok
    assert roster_service.create_class(TEACHER_A, "Year 10 Maths").ok

    classes = roster_service.list_classes(TEACHER_A)

    assert [c.name for c in classes] == ["Year 9 Maths", "Year 10 Maths"]
    assert all(c.code is None for c in classes)
    assert roster_service.list_classes(TEACHER_B) == []


@pytest.mark.parametrize(
    "name, message",
    [
        ("   ", "Give the class a name"),
        ("x" * (CLASS_NAME_MAX_CHARS + 1), "under 60 characters"),
        ("year 9 MATHS", "already have a class with that name"),
    ],
)
def test_a_bad_or_repeated_class_name_is_refused(store: _Store, name: str, message: str) -> None:
    roster_service.create_class(TEACHER_A, "Year 9 Maths")

    outcome = roster_service.create_class(TEACHER_A, name)

    assert not outcome.ok and message in outcome.message
    assert len(store.classes) == 1


def test_another_teacher_may_reuse_a_class_name(store: _Store) -> None:
    roster_service.create_class(TEACHER_A, "Year 9 Maths")
    assert roster_service.create_class(TEACHER_B, "Year 9 Maths").ok


def test_renaming_only_works_on_your_own_class(store: _Store) -> None:
    roster_service.create_class(TEACHER_A, "Year 9 Maths")
    mine = _class(store, "Year 9 Maths")

    assert roster_service.rename_class(TEACHER_A, mine.id, "Set 1").ok
    assert mine.name == "Set 1"
    refused = roster_service.rename_class(TEACHER_B, mine.id, "Stolen")
    assert not refused.ok and mine.name == "Set 1"


def test_codes_are_per_class(store: _Store) -> None:
    roster_service.create_class(TEACHER_A, "Year 9 Maths")
    roster_service.create_class(TEACHER_A, "Year 10 Maths")
    y9, y10 = _class(store, "Year 9 Maths"), _class(store, "Year 10 Maths")

    code_9 = roster_service.rotate_class_code(TEACHER_A, y9.id)
    code_10 = roster_service.rotate_class_code(TEACHER_A, y10.id)
    new_9 = roster_service.rotate_class_code(TEACHER_A, y9.id)

    assert y10.code == code_10, "a new Year 9 code must not revoke Year 10's"
    assert y9.code == new_9 != code_9


def test_a_teacher_cannot_issue_a_code_for_someone_elses_class(store: _Store) -> None:
    roster_service.create_class(TEACHER_A, "Year 9 Maths")
    with pytest.raises(ValueError):
        roster_service.rotate_class_code(TEACHER_B, _class(store, "Year 9 Maths").id)


def test_a_code_without_a_class_makes_my_class_like_the_old_sql(store: _Store) -> None:
    code = roster_service.rotate_class_code(TEACHER_A)

    [made] = roster_service.list_classes(TEACHER_A)
    assert made.name == DEFAULT_CLASS_NAME and made.code == code
    # Again: the same class, a new code - no second "My class".
    assert roster_service.rotate_class_code(TEACHER_A) != code
    assert len(roster_service.list_classes(TEACHER_A)) == 1


def test_joining_puts_the_student_in_that_class_and_with_that_teacher(store: _Store) -> None:
    roster_service.create_class(TEACHER_A, "Year 9 Maths")
    roster_service.create_class(TEACHER_A, "Year 10 Maths")
    y10 = _class(store, "Year 10 Maths")
    code = roster_service.rotate_class_code(TEACHER_A, y10.id)

    assert roster_service.join_class("usr_s02", code.lower()).ok

    student = _user(store, "usr_s02")
    assert (student.teacher_id, student.class_id) == (TEACHER_A, y10.id)


def test_another_code_moves_the_student_to_the_new_class(store: _Store) -> None:
    roster_service.create_class(TEACHER_A, "Year 9 Maths")
    roster_service.create_class(TEACHER_B, "Chemistry")
    code_a = roster_service.rotate_class_code(TEACHER_A, _class(store, "Year 9 Maths").id)
    code_b = roster_service.rotate_class_code(TEACHER_B, _class(store, "Chemistry").id)

    roster_service.join_class("usr_s01", code_a)
    roster_service.join_class("usr_s01", code_b)

    student = _user(store, "usr_s01")
    assert (student.teacher_id, student.class_id) == (TEACHER_B, _class(store, "Chemistry").id)


def test_leaving_and_being_removed_clear_the_class_too(store: _Store) -> None:
    roster_service.create_class(TEACHER_A, "Year 9 Maths")
    code = roster_service.rotate_class_code(TEACHER_A, _class(store, "Year 9 Maths").id)
    roster_service.join_class("usr_s01", code)
    roster_service.join_class("usr_s02", code)

    roster_service.leave_class("usr_s01")
    roster_service.remove_from_roster(TEACHER_A, "usr_s02")

    for student_id in ("usr_s01", "usr_s02"):
        student = _user(store, student_id)
        assert (student.teacher_id, student.class_id) == (None, None)


def test_only_an_empty_class_can_be_deleted_and_its_code_dies_with_it(store: _Store) -> None:
    roster_service.create_class(TEACHER_A, "Year 9 Maths")
    y9 = _class(store, "Year 9 Maths")
    code = roster_service.rotate_class_code(TEACHER_A, y9.id)
    roster_service.join_class("usr_s01", code)

    refused = roster_service.delete_class(TEACHER_A, y9.id)
    assert not refused.ok and "empty" in refused.message

    roster_service.leave_class("usr_s01")
    assert roster_service.delete_class(TEACHER_A, y9.id).ok
    assert roster_service.list_classes(TEACHER_A) == []
    assert not roster_service.join_class("usr_s02", code).ok


def test_a_teacher_cannot_delete_someone_elses_class(store: _Store) -> None:
    roster_service.create_class(TEACHER_A, "Year 9 Maths")
    assert not roster_service.delete_class(TEACHER_B, _class(store, "Year 9 Maths").id).ok
    assert len(store.classes) == 1


# --------------------------------------------------------------------------
# What a student is told
# --------------------------------------------------------------------------
def test_a_student_learns_their_class_teacher_and_school(store: _Store) -> None:
    roster_service.create_class(TEACHER_A, "Year 9 Maths")
    code = roster_service.rotate_class_code(TEACHER_A, _class(store, "Year 9 Maths").id)
    roster_service.join_class("usr_s01", code)

    membership = roster_service.my_class(_user(store, "usr_s01"))

    assert membership == ClassMembership(
        teacher_name="Ms Rao", class_name="Year 9 Maths", teacher_school="Greenfield School"
    )


def test_a_student_in_no_class_has_no_membership(store: _Store) -> None:
    assert roster_service.my_class(_user(store, "usr_s02")) is None


def test_a_failed_lookup_still_says_they_have_a_teacher(
    store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before migration 013 my_class() does not exist; "your teacher" beats "no class"."""
    student = _user(store, "usr_s01")
    student.teacher_id = TEACHER_A

    def boom(_student_id: str) -> None:
        raise RuntimeError("PGRST202 could not find the function public.my_class")

    import services.repository as repository_module

    monkeypatch.setattr(repository_module.get_repository(), "my_class", boom)

    assert roster_service.my_class(student) == ClassMembership(teacher_name="your teacher")


def test_a_missing_classes_table_is_reported_in_plain_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Old:
        def list_classes(self, _teacher_id: str) -> None:
            raise RuntimeError("{'code': 'PGRST205', 'message': \"Could not find the table 'public.classes'\"}")

    monkeypatch.setattr(roster_service, "get_repository", lambda: _Old())
    with pytest.raises(roster_service.ClassesNotSetUp) as raised:
        roster_service.list_classes(TEACHER_A)
    assert "013_classes_and_schools.sql" in str(raised.value)


# --------------------------------------------------------------------------
# The Supabase repository: what goes over the wire
# --------------------------------------------------------------------------
class _Query:
    def __init__(self, owner: "_Client", table: str) -> None:
        self.owner, self.table, self.ops = owner, table, []

    def __getattr__(self, name: str):
        def op(*args: Any, **_kwargs: Any) -> "_Query":
            self.ops.append((name, args))
            return self

        return op

    def execute(self) -> Any:
        self.owner.calls.append((self.table, self.ops))
        return SimpleNamespace(data=self.owner.rows.get(self.table, []))


class _Client:
    def __init__(self, rows: Optional[Dict[str, Any]] = None, rpc_data: Optional[Dict[str, Any]] = None) -> None:
        self.rows = rows or {}
        self.rpc_data = rpc_data or {}
        self.calls: List[Any] = []
        self.rpcs: List[Any] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def rpc(self, name: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self.rpcs.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.rpc_data.get(name)))


def test_supabase_lists_classes_with_their_live_codes() -> None:
    client = _Client(
        rows={
            "classes": [
                {"id": "cls_1", "teacher_id": TEACHER_A, "name": "Year 9 Maths"},
                {"id": "cls_2", "teacher_id": TEACHER_A, "name": "Year 10 Maths"},
            ],
            "class_invites": [{"code": "ABC234", "class_id": "cls_2"}],
        }
    )

    classes = SupabaseRepository(client).list_classes(TEACHER_A)

    assert [(c.name, c.code) for c in classes] == [("Year 9 Maths", None), ("Year 10 Maths", "ABC234")]
    invite_ops = next(ops for table, ops in client.calls if table == "class_invites")
    assert ("eq", ("revoked", False)) in invite_ops


def test_supabase_sends_only_teacher_and_name_for_a_new_class() -> None:
    client = _Client(rows={"classes": [{"id": "cls_9", "teacher_id": TEACHER_A, "name": "Set 1"}]})

    made = SupabaseRepository(client).create_class(TEACHER_A, "Set 1")

    assert made.id == "cls_9"
    [(_table, ops)] = client.calls
    assert ops[0] == ("insert", ({"teacher_id": TEACHER_A, "name": "Set 1"},))


def test_supabase_rotates_one_class_or_falls_back_to_the_old_call() -> None:
    client = _Client(rpc_data={"rotate_class_code": "XYZ789"})
    repo = SupabaseRepository(client)

    assert repo.rotate_class_code(TEACHER_A, "cls_1") == "XYZ789"
    repo.rotate_class_code(TEACHER_A)

    assert client.rpcs == [
        ("rotate_class_code", {"p_class_id": "cls_1"}),
        ("rotate_class_code", {}),
    ]


def test_supabase_asks_my_class_for_the_names() -> None:
    client = _Client(
        rpc_data={"my_class": [{"class_id": "cls_1", "class_name": "Year 9 Maths",
                                "teacher_name": "Ms Rao", "teacher_school": None}]}
    )

    membership = SupabaseRepository(client).my_class("usr_s01")

    assert membership == ClassMembership(teacher_name="Ms Rao", class_name="Year 9 Maths")
    assert client.rpcs == [("my_class", {})]


# --------------------------------------------------------------------------
# Schools
# --------------------------------------------------------------------------
def test_the_demo_lists_teachers_schools_only(store: _Store, monkeypatch: pytest.MonkeyPatch) -> None:
    from services import state

    store.users.append(User(display_name="Typo", role=Role.STUDENT, school="Grenfeld Skool"))
    store.users.append(User(display_name="Mr Lee", role=Role.TEACHER, school="Alder Academy"))
    monkeypatch.setattr(state, "get_users", lambda: store.users)

    assert school_service.list_schools() == ["Alder Academy", "Greenfield School"]


def test_a_configured_app_asks_list_schools_on_a_client_with_no_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(rpc_data={"list_schools": [{"school": "Alder Academy"}, {"school": None}]})
    monkeypatch.setattr(auth_service, "anonymous_client", lambda: client)
    monkeypatch.setattr(
        school_service, "get_settings", lambda: SimpleNamespace(supabase_configured=True)
    )

    assert school_service.list_schools() == ["Alder Academy"]
    assert client.rpcs == [("list_schools", {})]


def test_a_school_list_that_cannot_be_read_is_empty_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Broken(_Client):
        def rpc(self, name: str, params: Optional[Dict[str, Any]] = None) -> Any:
            raise RuntimeError("PGRST202 could not find the function public.list_schools")

    monkeypatch.setattr(auth_service, "anonymous_client", lambda: _Broken())
    monkeypatch.setattr(
        school_service, "get_settings", lambda: SimpleNamespace(supabase_configured=True)
    )

    assert school_service.list_schools() == []


def test_a_school_over_the_limit_is_refused() -> None:
    assert school_service.school_problem("x" * SCHOOL_MAX_CHARS) is None
    assert "80 characters" in school_service.school_problem("x" * (SCHOOL_MAX_CHARS + 1))
    assert school_service.school_problem("") is None


def _signing_up(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    sent: Dict[str, Any] = {}

    class _Auth:
        def sign_up(self, credentials: Dict[str, Any]) -> Any:
            sent.update(credentials)
            return SimpleNamespace(session=object())

    monkeypatch.setattr(auth_service, "session_client", lambda: SimpleNamespace(auth=_Auth()))
    monkeypatch.setattr(auth_service, "_clear_cached_profile", lambda: None)
    return sent


def test_sign_up_sends_the_school_and_year_as_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _signing_up(monkeypatch)

    outcome = auth_service.sign_up(
        "sam@school.test", "Student42x", "Sam", "  Greenfield  School ", 9
    )

    assert outcome.ok
    assert sent["options"] == {
        "data": {"full_name": "Sam", "school": "Greenfield School", "year_group": 9}
    }
    assert "role" not in str(sent)


def test_sign_up_without_school_or_year_sends_only_the_name(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _signing_up(monkeypatch)
    auth_service.sign_up("sam@school.test", "Student42x", "Sam")
    assert sent["options"] == {"data": {"full_name": "Sam"}}


@pytest.mark.parametrize(
    "school, year, message",
    [("x" * (SCHOOL_MAX_CHARS + 1), None, "80 characters"), (None, 6, "between 7 and 11")],
)
def test_sign_up_refuses_a_bad_school_or_year_before_supabase(
    monkeypatch: pytest.MonkeyPatch, school: Optional[str], year: Optional[int], message: str
) -> None:
    sent = _signing_up(monkeypatch)
    outcome = auth_service.sign_up("sam@school.test", "Student42x", "Sam", school, year)
    assert not outcome.ok and message in outcome.message
    assert sent == {}


def _saving_profile(monkeypatch: pytest.MonkeyPatch, current_school: Optional[str]) -> List[Dict[str, Any]]:
    written: List[Dict[str, Any]] = []
    me = User(id="usr_s01", display_name="Sam", school=current_school)
    monkeypatch.setattr(auth_service, "current_user", lambda: me)
    monkeypatch.setattr(
        auth_service,
        "_write_profile",
        lambda changes, success: written.append(changes) or auth_service.AuthOutcome(True, success),
    )
    return written


def test_profile_sends_the_school_only_when_it_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    """So saving a name keeps working on a database without migration 013."""
    written = _saving_profile(monkeypatch, "Greenfield School")

    auth_service.update_profile("Sam", 9, "Greenfield  School")
    auth_service.update_profile("Sam", 9, "Alder Academy")
    auth_service.update_profile("Sam", 9, None)
    auth_service.update_profile("Sam", 9)

    assert [c.get("school", "<not sent>") for c in written] == [
        "<not sent>", "Alder Academy", None, "<not sent>"
    ]


def test_an_admin_made_teacher_gets_their_school_in_the_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: List[Dict[str, Any]] = []

    class _Admin:
        def create_user(self, attributes: Dict[str, Any]) -> Any:
            created.append(attributes)
            return SimpleNamespace(user=SimpleNamespace(id="11111111-2222-3333-4444-555555555555"))

    client = _Client(rpc_data={"admin_make_teacher": "usr_new"})
    client.auth = SimpleNamespace(admin=_Admin())
    monkeypatch.setattr(admin_service, "_admin_client", lambda: (client, None))

    outcome = admin_service.create_teacher(
        "Ms Rao", "rao@school.test", "Temporary1", " Greenfield  School"
    )

    assert outcome.ok
    assert created[0]["user_metadata"]["school"] == "Greenfield School"
    assert created[0]["user_metadata"]["must_change_password"] is True


def test_the_admin_teacher_list_carries_the_school(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client(rpc_data={"admin_list_teachers": [
        {"profile_id": "usr_t", "display_name": "Ms Rao", "student_count": 3, "school": "Greenfield School"},
        {"profile_id": "usr_u", "display_name": "Mr Diaz", "student_count": 0},
    ]})
    monkeypatch.setattr(admin_service, "_admin_client", lambda: (client, None))

    rows, problem = admin_service.list_teachers()

    assert problem is None
    assert [(r.display_name, r.school) for r in rows] == [
        ("Ms Rao", "Greenfield School"), ("Mr Diaz", None)
    ]


# --------------------------------------------------------------------------
# Migration 013, read rather than run
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _function(sql: str, signature: str) -> str:
    start = sql.index(f"function public.{signature}")
    return sql[start: sql.index("$fn$;", start)]


def test_the_join_rate_limit_from_008_survives(sql: str) -> None:
    body = _function(sql, "join_class(p_code text)")
    assert "class_join_attempt_windows" in body and "attempt_count > 10" in body
    assert "set teacher_id = found_teacher, class_id = found_class" in body


@pytest.mark.parametrize(
    "signature",
    ["redeem_teacher_invite(code text)", "admin_make_teacher(p_auth_user_id uuid)"],
)
def test_every_promotion_clears_the_class(sql: str, signature: str) -> None:
    body = _function(sql, signature)
    assert re.search(r"set role = 'teacher', teacher_id = null, class_id = null", body)


@pytest.mark.parametrize(
    "signature", ["leave_class()", "remove_from_roster(p_student_id text)"]
)
def test_leaving_clears_both(sql: str, signature: str) -> None:
    assert "set teacher_id = null, class_id = null" in _function(sql, signature)


def test_releasing_a_demoted_teachers_students_clears_their_class(sql: str) -> None:
    assert "set teacher_id = null, class_id = null" in _function(
        sql, "admin_demote_teacher("
    )


def test_only_list_schools_is_open_to_signed_out_visitors(sql: str) -> None:
    grants_to_anon = re.findall(r"grant execute on function public\.(\w+)\([^)]*\) to anon", sql)
    assert grants_to_anon == ["list_schools"]
    for name in ("my_class()", "rotate_class_code(text)", "rotate_class_code()", "join_class(text)"):
        assert f"revoke all on function public.{name} from public, anon;" in sql


def test_the_sign_up_trigger_still_makes_only_students(sql: str) -> None:
    body = _function(sql, "handle_new_auth_user()")
    assert "'student'" in body and "'teacher'" not in body
    assert "->> 'school'" in body and "->> 'year_group'" in body


def test_classes_are_closed_to_everyone_but_their_teacher(sql: str) -> None:
    assert "create policy classes_own on public.classes" in sql
    assert "using (teacher_id = public.app_profile_id() and public.app_is_teacher())" in sql
    assert "grant update (name) on public.classes to authenticated;" in sql
    assert "grant insert (teacher_id, name) on public.classes to authenticated;" in sql
    assert "revoke all on public.classes from public, anon, authenticated;" in sql


def test_existing_codes_and_students_move_into_my_class(sql: str) -> None:
    assert "'My class'" in sql
    assert "update public.class_invites i" in sql and "update public.profiles s" in sql
    # The old app's call keeps working until the new code is deployed.
    assert "create or replace function public.rotate_class_code()" in sql


def test_the_school_grant_survives_a_policies_rerun() -> None:
    policies = (ROOT / "db" / "policies.sql").read_text(encoding="utf-8")
    assert "grant update (school) on public.profiles to authenticated" in policies
    assert "column_name = 'school'" in policies, "guarded, so policies.sql still runs before 013"


def test_setup_all_includes_013_and_its_school_column() -> None:
    setup = (ROOT / "db" / "setup_all.sql").read_text(encoding="utf-8")
    assert "-- Source: db/migrations/013_classes_and_schools.sql" in setup
    assert setup.index("013_classes_and_schools") < setup.index("-- Source: db/policies.sql")
    schema = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    assert "profiles_school_length" in schema and "profiles_school_length" in setup


# --------------------------------------------------------------------------
# The pages
# --------------------------------------------------------------------------
def _run(page: str, users: List[User], classes: List[Classroom], user_id: Optional[str]):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "views" / page), default_timeout=60)
    at.session_state["users"] = users
    at.session_state["classes"] = classes
    if user_id:
        at.session_state["current_user_id"] = user_id
    at.run()
    assert not at.exception, at.exception
    return at


def _people() -> List[User]:
    return [
        User(id="usr_t", display_name="Ms Rao", role=Role.TEACHER, school="Greenfield School"),
        User(id="usr_s1", display_name="Sam", role=Role.STUDENT, teacher_id="usr_t",
             class_id="cls_9", year_group=9, school="Greenfield School"),
        User(id="usr_s2", display_name="Ana", role=Role.STUDENT, teacher_id="usr_t",
             class_id="cls_10", year_group=10),
    ]


def _two_classes() -> List[Classroom]:
    return [
        Classroom(id="cls_9", teacher_id="usr_t", name="Year 9 Maths", code="ABC234"),
        Classroom(id="cls_10", teacher_id="usr_t", name="Year 10 Maths"),
    ]


def test_the_teacher_page_shows_each_class_its_code_and_the_class_column() -> None:
    at = _run("my_class.py", _people(), _two_classes(), "usr_t")

    page = " ".join(m.value for m in at.markdown)
    assert "Year 9 Maths" in page and "Year 10 Maths" in page
    assert [c.value for c in at.code] == ["ABC234"]
    labels = [b.label for b in at.button]
    assert "Issue a new code" in labels and "Issue a class code" in labels
    table = at.dataframe[0].value
    assert list(table.columns) == ["Student", "Class", "Year", "School", "Pieces of work"]
    assert dict(zip(table["Student"], table["Class"])) == {"Ana": "Year 10 Maths", "Sam": "Year 9 Maths"}


def test_before_013_the_teacher_page_says_so_instead_of_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What a live teacher sees if the code is deployed before the migration."""

    def not_set_up(_teacher_id: str) -> None:
        raise roster_service.ClassesNotSetUp(roster_service.NOT_SET_UP_MESSAGE)

    monkeypatch.setattr(roster_service, "list_classes", not_set_up)
    at = _run("my_class.py", _people(), [], "usr_t")

    assert [e.value for e in at.error] == [roster_service.NOT_SET_UP_MESSAGE]
    assert "Issue a class code" not in [b.label for b in at.button]


def test_the_teacher_can_show_one_class(monkeypatch: pytest.MonkeyPatch) -> None:
    at = _run("my_class.py", _people(), _two_classes(), "usr_t")
    next(s for s in at.selectbox if s.label == "Show").select("cls_10").run()
    assert list(at.dataframe[0].value["Student"]) == ["Ana"]


def test_a_teacher_adds_a_class_from_the_page() -> None:
    at = _run("my_class.py", _people(), _two_classes(), "usr_t")
    next(t for t in at.text_input if t.label == "Add a class").input("Year 11 Maths")
    next(b for b in at.button if b.label == "Add class").click().run()
    assert not at.exception, at.exception
    assert "Year 11 Maths" in [c.name for c in at.session_state["classes"]]


def test_the_student_page_names_the_class_and_the_teacher() -> None:
    at = _run("my_class.py", _people(), _two_classes(), "usr_s1")
    [line] = [m.value for m in at.success]
    assert line == "You are in Year 9 Maths with Ms Rao."
    assert any("Greenfield School" in c.value for c in at.caption)


def test_the_schools_page_lists_names_as_plain_text() -> None:
    teachers = [
        User(id="usr_t1", display_name="A", role=Role.TEACHER, school="Greenfield School"),
        User(id="usr_t2", display_name="B", role=Role.TEACHER, school="[Click](https://example.com)"),
    ]
    at = _run("schools.py", teachers, [], None)
    listing = next(m.value for m in at.markdown if "Greenfield" in m.value)
    assert "\\[Click\\]\\(https://example\\.com\\)" in listing, "a typed link must not become a link"


def test_the_sign_up_form_asks_for_school_and_year() -> None:
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "views" / "sign_in.py"), default_timeout=60)
    at.run()
    labels = [s.label for s in at.selectbox]
    # With no Supabase configured the page explains instead of showing the form;
    # either way nothing may crash, and when the form is there it has both boxes.
    assert not at.exception, at.exception
    if any(b.label == "Create account" for b in at.button):
        assert "School" in labels and "Year group" in labels
