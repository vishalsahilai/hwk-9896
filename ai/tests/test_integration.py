import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.ai.router import create_router
from app.ai.schemas import LeaveProposal, Selection

from .conftest import call


@pytest.fixture
def client_factory(build, hr):
    def make(replies, user=None):
        service, _model = build(replies)

        async def auth():
            return user or hr

        async def get_service():
            return service

        app = FastAPI()
        app.include_router(create_router(auth, get_service), prefix="/api")
        return TestClient(app)

    return make


def test_exact_chat_contract(client_factory):
    c = client_factory(
        [call("get_headcount"), AIMessage(content=""), Selection(fact_ids=[1])]
    )
    r = c.post("/api/ai/chat", json={"message": "headcount", "history": []})
    assert r.status_code == 200
    assert set(r.json()) == {"answer", "tools_used", "ai_generated"}


def test_exact_summary_contract(client_factory):
    r = client_factory([Selection(fact_ids=[1, 2, 3])]).post(
        "/api/ai/summary", json={"kpis": {"headcount": 3}}
    )
    assert r.status_code == 200 and set(r.json()) == {"bullets"}


def test_exact_leave_contract(client_factory):
    proposal = LeaveProposal(
        leave_type="sick",
        start_date="2026-10-25",
        end_date="2026-10-25",
        reason="fever",
    )
    r = client_factory([proposal]).post(
        "/api/ai/smart-leave", json={"text": "Tomorrow fever"}
    )
    assert r.status_code == 200 and r.json() == proposal.model_dump(mode="json")


@pytest.mark.parametrize(
    "path,body",
    [
        ("chat", {"message": "hi"}),
        ("summary", {"kpis": {}}),
        ("smart-leave", {"text": "tomorrow fever"}),
    ],
)
def test_unconfigured_auth_fails_closed(path, body):
    app = FastAPI()
    app.include_router(create_router(), prefix="/api")
    for headers in ({}, {"Authorization": "Bearer invented"}):
        r = TestClient(app).post("/api/ai/" + path, json=body, headers=headers)
        assert r.status_code == 401 and r.json()["detail"]["code"] == "AUTH_REQUIRED"


def test_error_contract(client_factory, employee):
    r = client_factory([], employee).post("/api/ai/summary", json={"kpis": {}})
    assert r.status_code == 403 and set(r.json()["detail"]) == {"code", "message"}


@pytest.mark.skip(
    reason="No backend JWT dependency, PostgreSQL models/services, or application exists in this checkout."
)
def test_real_backend_postgres_and_jwt():
    pass


def test_validation_error_envelope(client_factory):
    r = client_factory([]).post(
        "/api/ai/chat", json={"message": "hello", "role": "admin"}
    )
    assert r.status_code == 422
    assert set(r.json()["detail"]) == {"code", "message"}


@pytest.mark.parametrize(
    "flag,value", [("must_change_password", True), ("is_active", False)]
)
def test_account_flags_through_route(client_factory, hr, flag, value):
    setattr(hr, flag, value)
    r = client_factory([]).post("/api/ai/chat", json={"message": "hello"})
    assert r.status_code == 403


def test_no_fake_production_auth_or_services():
    import ast
    from pathlib import Path

    module = Path(__file__).parent.parent
    for path in module.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(
                    ("sqlalchemy", "psycopg", "tests", "subprocess")
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec"}
