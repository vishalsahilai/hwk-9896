import json
from datetime import date
from typing import Annotated

from fastapi import HTTPException
from langchain_core.tools import StructuredTool
from pydantic import Field, TypeAdapter, ValidationError

from . import schemas as s
from .dates import date_range
from .exceptions import AIError
from .services import Backend

# Name -> arguments, result, roles, description. No identity argument is model-controlled.
SPECS = {
    "get_headcount": (
        s.Department,
        s.Headcount,
        {"admin", "hr"},
        "Count active employees, optionally by department.",
    ),
    "get_attendance_summary": (
        s.DateRange,
        s.Attendance,
        {"admin", "hr", "employee"},
        "Attendance totals and authoritative rate over explicit dates or relative period. Employees: own only.",
    ),
    "get_late_comers": (
        s.LateArgs,
        s.LateResult,
        {"admin", "hr"},
        "Rank employees by late count over dates or relative period; at most 20.",
    ),
    "get_leave_summary": (
        s.DateRange,
        s.LeaveSummary,
        {"admin", "hr"},
        "Names on leave and counts by type for dates or relative period.",
    ),
    "get_my_leave_balance": (
        s.NoArgs,
        s.Balances,
        {"admin", "hr", "employee"},
        "Current user's own leave quotas, used, pending and remaining. Requires linked employee.",
    ),
    "get_payroll_summary": (
        s.PayrollArgs,
        s.Payroll,
        {"admin"},
        "Admin-only payroll gross, net, average and headcount for YYYY-MM.",
    ),
    "search_employees": (
        s.SearchArgs,
        s.Employees,
        {"admin", "hr"},
        "Search directory by name/code/department; no salaries or private contact details.",
    ),
}


class Toolset:
    def __init__(self, backend: Backend, user: s.User, today: date):
        self.backend, self.user, self.today = backend, user, today
        self.names = [
            n
            for n, (_, _, roles, _) in SPECS.items()
            if user.role in roles
            and (n != "get_my_leave_balance" or user.employee_id is not None)
        ]

    def definitions(self):
        tools = []
        for name in self.names:

            async def invoke(_name=name, **kwargs):
                return await self.execute(_name, kwargs)

            args, _, _, description = SPECS[name]
            tools.append(
                StructuredTool.from_function(
                    coroutine=invoke,
                    name=name,
                    description=description,
                    args_schema=args,
                )
            )
        return tools

    async def execute(self, name: str, arguments: dict) -> dict:
        if name not in self.names:
            raise AIError(
                "AI_FORBIDDEN",
                "This information is outside your permitted access.",
                403,
            )
        args_type, result_type, _, _ = SPECS[name]
        try:
            args = args_type.model_validate(arguments).model_dump(exclude_none=True)
            if issubclass(args_type, s.DateRange):
                args = date_range(args, self.today)
            if self.user.role == "employee":
                if self.user.employee_id is None:
                    raise AIError(
                        "AI_FORBIDDEN",
                        "No employee profile is linked to your login.",
                        403,
                    )
                if args.get("department"):
                    raise AIError(
                        "AI_FORBIDDEN", "Only your personal records are available.", 403
                    )
            if args.get("department"):
                departments = TypeAdapter(
                    Annotated[list[s.Name], Field(max_length=200)]
                ).validate_python(await self.backend.departments(self.user))
                key = args["department"].casefold().removesuffix(" team").strip()
                match = next((d for d in departments if d.casefold() == key), None)
                if not match:
                    return {
                        "notice": "Unknown department. Available departments: "
                        + ", ".join(departments[:20])
                    }
                args["department"] = match
            result = await self.backend.read(name, self.user, args)
            # Reject unexpected fields rather than letting credentials leak through.
            validated = result_type.model_validate(result).model_dump(mode="json")
            if len(json.dumps(validated)) > 24000:
                raise ValueError("Oversize tool result")
            return validated
        except AIError:
            raise
        except HTTPException as exc:
            if exc.status_code in {401, 403}:
                raise AIError(
                    "AI_FORBIDDEN",
                    "The backend denied access to this information.",
                    exc.status_code,
                ) from None
            raise AIError(
                "AI_TOOL_FAILED", "The requested data is unavailable.", exc.status_code
            ) from None
        except ValidationError:
            raise AIError(
                "AI_TOOL_INVALID",
                "The requested data could not be validated. Please use the dashboard.",
                422,
            ) from None
        except Exception:  # noqa: BLE001 -- sanitize errors at the external boundary
            raise AIError(
                "AI_TOOL_FAILED", "The requested data is temporarily unavailable."
            ) from None
