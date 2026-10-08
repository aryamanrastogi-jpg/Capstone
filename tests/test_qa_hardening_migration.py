from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent


def _sql_definition(source: str, signature: str) -> str:
    start = source.lower().index(signature.lower())
    end = source.index(";", start) + 1
    statement = re.sub(r"--[^\n]*", "", source[start:end])
    return " ".join(statement.lower().split())


def test_migration_008_matches_the_fresh_schema_and_policy_definitions():
    migration = (ROOT / "db/migrations/008_qa_hardening.sql").read_text()
    schema = (ROOT / "db/schema.sql").read_text()
    policies = (ROOT / "db/policies.sql").read_text()

    assert "is_archived     boolean not null default false" in schema
    assert "owner_id        text references public.profiles (id) on delete set null" in schema
    assert "add column if not exists is_archived boolean not null default false" in migration
    assert "foreign key (owner_id) references public.profiles(id) on delete set null" in migration

    for definition in (
        "create policy assessments_select on public.assessments",
        "create policy questions_select on public.questions",
        "create view public.student_questions as",
        "create policy submissions_insert_own on public.submissions",
        "create policy grading_results_insert on public.grading_results",
        "create view public.student_grading_results as",
        "create view public.teacher_grading_results as",
    ):
        assert _sql_definition(migration, definition) == _sql_definition(policies, definition)

    assert "create table if not exists public.class_join_attempt_windows" in migration
    assert "create or replace function public.join_class(p_code text)" in migration
    assert "create or replace function public.delete_my_account()" in migration


def test_migration_008_is_documented_to_run_before_deploy():
    migrations_readme = (ROOT / "db/migrations/README.md").read_text()
    deployment = (ROOT / "docs/deployment.md").read_text()

    assert "`008_qa_hardening.sql`" in migrations_readme
    assert "Run `008` before deploying code" in migrations_readme
    assert "Run migration 008 in the Supabase SQL editor before deploying" in deployment
