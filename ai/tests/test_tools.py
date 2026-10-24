import pytest

from app.ai.exceptions import AIError
from app.ai.schemas import User
from app.ai.tools import SPECS, Toolset

from .conftest import TODAY

ARGS = {
    "get_attendance_summary": {"period": "today"},
    "get_late_comers": {"period": "this month"},
    "get_leave_summary": {"period": "today"},
    "get_payroll_summary": {"month": "2026-10"},
    "search_employees": {"text": "Test"},
}


@pytest.mark.parametrize("name", SPECS)
async def test_seven_tools(name, backend):
    user = User(id=1, role="admin", employee_id=1)
    result = await Toolset(backend, user, TODAY).execute(name, ARGS.get(name, {}))
    assert result == SPECS[name][1].model_validate(backend.results[name]).model_dump(
        mode="json"
    )
    assert backend.calls[0][1] == user


@pytest.mark.parametrize("role,expected", [("admin", 7), ("hr", 6), ("employee", 2)])
async def test_tool_visibility(role, expected, backend):
    tools = Toolset(backend, User(id=1, role=role, employee_id=1), TODAY)
    assert len(tools.definitions()) == expected


@pytest.mark.parametrize(
    "name",
    [
        "get_headcount",
        "get_late_comers",
        "get_leave_summary",
        "get_payroll_summary",
        "search_employees",
        "raw_sql",
    ],
)
async def test_employee_forbidden(name, backend, employee):
    with pytest.raises(AIError) as e:
        await Toolset(backend, employee, TODAY).execute(name, {})
    assert e.value.status_code == 403
    assert not backend.calls


async def test_own_scope_and_identity_rejected(backend, employee):
    tools = Toolset(backend, employee, TODAY)
    await tools.execute("get_attendance_summary", {"period": "today"})
    assert backend.calls[0][1].employee_id == 22
    with pytest.raises(AIError):
        await tools.execute("get_my_leave_balance", {"employee_id": 999})


@pytest.mark.parametrize("dept", ["sales", "SALES", "Sales team"])
async def test_case_department(dept, backend, hr):
    await Toolset(backend, hr, TODAY).execute("get_headcount", {"department": dept})
    assert backend.calls[-1][2]["department"] == "Sales"


async def test_unknown_department(backend, hr):
    result = await Toolset(backend, hr, TODAY).execute(
        "get_headcount", {"department": "Slaes"}
    )
    assert "Sales" in result["notice"] and not backend.calls


async def test_output_sensitive_fields_rejected(backend, hr):
    backend.results["search_employees"]["employees"][0]["salary"] = 999
    with pytest.raises(AIError):
        await Toolset(backend, hr, TODAY).execute("search_employees", {"text": "Test"})


@pytest.mark.parametrize(
    "args",
    [
        {"period": "today", "start_date": "2026-10-01"},
        {"start_date": "2026-10-30", "end_date": "2026-10-01"},
        {"period": "not real"},
    ],
)
async def test_bad_ranges(args, backend, hr):
    with pytest.raises(AIError):
        await Toolset(backend, hr, TODAY).execute("get_attendance_summary", args)


async def test_hr_no_payroll(backend, hr):
    with pytest.raises(AIError):
        await Toolset(backend, hr, TODAY).execute(
            "get_payroll_summary", {"month": "2026-10"}
        )


async def test_employee_department_blocked(backend, employee):
    with pytest.raises(AIError) as e:
        await Toolset(backend, employee, TODAY).execute(
            "get_attendance_summary", {"period": "today", "department": "Sales"}
        )
    assert e.value.status_code == 403


async def test_backend_authorization_preserved(backend, hr):
    from fastapi import HTTPException

    async def denied(*args):
        raise HTTPException(403, "SECRET PRIVATE DETAIL")

    backend.read = denied
    with pytest.raises(AIError) as e:
        await Toolset(backend, hr, TODAY).execute("get_headcount", {})
    assert e.value.status_code == 403
    assert "SECRET" not in str(e.value.detail)


async def test_unlinked_employee_cannot_read(backend):
    user = User(id=8, role="employee")
    assert "get_my_leave_balance" not in Toolset(backend, user, TODAY).names
    with pytest.raises(AIError) as e:
        await Toolset(backend, user, TODAY).execute(
            "get_attendance_summary", {"period": "today"}
        )
    assert e.value.status_code == 403 and not backend.calls


async def test_tool_arguments_and_limits(backend, hr):
    with pytest.raises(AIError):
        await Toolset(backend, hr, TODAY).execute(
            "get_late_comers", {"period": "today", "limit": 21}
        )
