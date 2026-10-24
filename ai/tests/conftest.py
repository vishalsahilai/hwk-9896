from collections import deque
from datetime import date

import pytest
from langchain_core.messages import AIMessage

from app.ai.config import Settings
from app.ai.exceptions import AIError
from app.ai.guard import AIService
from app.ai.providers import Provider, ProviderManager
from app.ai.schemas import User

TODAY = date(2026, 10, 24)


class FakeModel:
    def __init__(self, replies):
        self.replies = deque(replies)
        self.messages = []
        self.tools = []
        self.schema = None

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def with_structured_output(self, schema, **kwargs):
        self.schema = schema
        return self

    async def ainvoke(self, messages, config=None):
        self.messages.append(messages)
        result = self.replies.popleft()
        if isinstance(result, Exception):
            raise result
        if callable(result):
            return await result()
        return result


class FixtureBackend:
    """Test-only fixtures; never imported by production modules."""

    def __init__(self):
        self.calls = []
        self.policy_data = {
            "office_start": "09:00:00",
            "grace_minutes": 15,
            "half_day_hours": 5,
            "weekend_days": [5, 6],
            "leave_quotas": {"annual": 14, "sick": 8, "casual": 10, "unpaid": None},
        }
        self.dashboard_data = {
            "headcount": 3,
            "present_today": 2,
            "late_today": 1,
            "pending_approvals": 0,
        }
        self.results = {
            "get_headcount": {
                "total": 3,
                "departments": [{"department": "Sales", "count": 3}],
            },
            "get_attendance_summary": {
                "present": 2,
                "late": 1,
                "half_day": 0,
                "absent": 0,
                "on_leave": 0,
                "attendance_rate": 100,
            },
            "get_late_comers": {
                "employees": [{"name": "Test Person", "late_count": 1}]
            },
            "get_leave_summary": {"employees": [], "counts": {}},
            "get_my_leave_balance": {
                "balances": [
                    {
                        "leave_type": "sick",
                        "quota": 8,
                        "used": 1,
                        "pending": 0,
                        "remaining": 7,
                    }
                ]
            },
            "get_payroll_summary": {
                "total_gross": 1500,
                "total_net": 1400,
                "average_salary": 1500,
                "employee_count": 1,
            },
            "search_employees": {
                "employees": [
                    {
                        "name": "Test Person",
                        "employee_code": "T001",
                        "department": "Sales",
                        "designation": "Tester",
                    }
                ]
            },
        }

    async def read(self, name, user, args):
        # Simulates independent service authorization, not real JWT/PostgreSQL integration.
        if user.role == "employee" and name not in {
            "get_my_leave_balance",
            "get_attendance_summary",
        }:
            raise AIError("AI_FORBIDDEN", "Forbidden", 403)
        if name == "get_payroll_summary" and user.role != "admin":
            raise AIError("AI_FORBIDDEN", "Forbidden", 403)
        self.calls.append((name, user, args))
        return self.results[name]

    async def departments(self, user):
        return ["Sales", "Engineering"]

    async def policy(self, user):
        return self.policy_data

    async def dashboard(self, user, context):
        return self.dashboard_data


class FixtureOperations:
    """In-memory rate limiter ONLY for deterministic contract tests."""

    def __init__(self):
        self.counts = {}
        self.logs = []

    async def reserve(self, user, feature, limit):
        n = self.counts.get(user.id, 0)
        if n >= limit:
            raise AIError("AI_RATE_LIMIT", "Please try again later.", 429)
        self.counts[user.id] = n + 1
        return str(n + 1)

    async def complete(self, key, record):
        self.logs.append(record)


@pytest.fixture
def backend():
    return FixtureBackend()


@pytest.fixture
def operations():
    return FixtureOperations()


@pytest.fixture
def hr():
    return User(id=1, role="hr", employee_id=11)


@pytest.fixture
def employee():
    return User(id=2, role="employee", employee_id=22)


@pytest.fixture
def admin():
    return User(id=3, role="admin")


@pytest.fixture
def build(backend, operations):
    def make(replies, settings=None):
        model = FakeModel(replies)
        service = AIService(
            backend,
            operations,
            ProviderManager([Provider("alibaba:test", model)]),
            settings or Settings(_env_file=None),
            clock=lambda: TODAY,
        )
        return service, model

    return make


def call(name, args=None, id="c1"):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args or {}, "id": id, "type": "tool_call"}],
    )
