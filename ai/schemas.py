from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Count = Annotated[int, Field(ge=0, strict=True)]
Money = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class User(Schema):
    id: int = Field(gt=0)
    role: Literal["admin", "hr", "employee"]
    employee_id: int | None = Field(None, gt=0)
    is_active: bool = True
    must_change_password: bool = False


class History(Schema):
    role: Literal["user", "assistant"]
    content: Text


class ChatRequest(Schema):
    message: Text
    history: list[History] = Field(default_factory=list, max_length=10)


class ChatResponse(Schema):
    answer: str = Field(min_length=1, max_length=20000)
    tools_used: list[str]
    ai_generated: Literal[True] = True


class LeaveRequest(Schema):
    text: Text


class LeaveProposal(Schema):
    leave_type: Literal["annual", "sick", "casual", "unpaid"]
    start_date: date
    end_date: date
    reason: Text

    @model_validator(mode="after")
    def dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End before start")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("Range too long")
        return self


class Selection(Schema):
    fact_ids: list[int] = Field(min_length=1, max_length=5)


class SummaryResponse(Schema):
    bullets: list[str] = Field(min_length=1, max_length=5)


class Department(Schema):
    department: Name | None = None


class DateRange(Department):
    start_date: date | None = None
    end_date: date | None = None
    period: (
        Literal[
            "today", "yesterday", "this month", "last month", "this week", "last week"
        ]
        | None
    ) = None


class LateArgs(DateRange):
    limit: int = Field(5, ge=1, le=20)


class PayrollArgs(Department):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class SearchArgs(Schema):
    text: Name


class NoArgs(Schema):
    pass


class DepartmentCount(Schema):
    department: Name
    count: Count


class Headcount(Schema):
    total: Count
    departments: list[DepartmentCount] = Field(max_length=200)


class Attendance(Schema):
    present: Count
    late: Count
    half_day: Count
    absent: Count
    on_leave: Count
    attendance_rate: float = Field(ge=0, le=100, allow_inf_nan=False)


class LateEmployee(Schema):
    name: Name
    late_count: Count


class LateResult(Schema):
    employees: list[LateEmployee] = Field(max_length=20)


class LeaveEmployee(Schema):
    name: Name
    leave_type: Name


class LeaveSummary(Schema):
    employees: list[LeaveEmployee] = Field(max_length=200)
    counts: dict[Name, Count] = Field(max_length=20)


class Balance(Schema):
    leave_type: Name
    quota: Money | None
    used: Money
    pending: Money
    remaining: Money | None


class Balances(Schema):
    balances: list[Balance] = Field(max_length=20)


class Payroll(Schema):
    total_gross: Money
    total_net: Money
    average_salary: Money
    employee_count: Count


class Employee(Schema):
    name: Name
    employee_code: Name
    department: Name
    designation: Name


class Employees(Schema):
    employees: list[Employee] = Field(max_length=50)


class KPIContext(Schema):
    start_date: date | None = None
    end_date: date | None = None
    department: Name | None = None

    @model_validator(mode="after")
    def valid_range(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End before start")
        return self


class DepartmentMoney(Schema):
    department: Name
    total_gross: Money
    total_net: Money


class DepartmentRate(Schema):
    department: Name
    rate: float = Field(ge=0, le=100, allow_inf_nan=False)


class AttendancePoint(Schema):
    date: date
    attendance_rate: float = Field(ge=0, le=100, allow_inf_nan=False)


class AuditEntry(Schema):
    action: Name
    entity: Name
    actor: Name


class KPIs(Schema):
    headcount: Count | None = None
    present_today: Count | None = None
    on_leave_today: Count | None = None
    late_today: Count | None = None
    pending_approvals: Count | None = None
    attrition_ytd: Money | None = None
    payroll_cost: Money | None = None
    avg_salary: Money | None = None
    headcount_by_dept: list[DepartmentCount] = Field(
        default_factory=list, max_length=200
    )
    payroll_cost_by_dept: list[DepartmentMoney] = Field(
        default_factory=list, max_length=200
    )
    gender: dict[str, Count] = Field(default_factory=dict, max_length=3)
    tenure: dict[str, Count] = Field(default_factory=dict, max_length=10)
    attendance_trend: list[AttendancePoint] = Field(
        default_factory=list, max_length=366
    )
    absenteeism_by_dept: list[DepartmentRate] = Field(
        default_factory=list, max_length=200
    )
    leave_by_type: dict[Name, Count] = Field(default_factory=dict, max_length=20)
    top_late_comers: list[LateEmployee] = Field(default_factory=list, max_length=20)
    recent_audit: list[AuditEntry] = Field(default_factory=list, max_length=10)
    context: KPIContext = Field(default_factory=KPIContext)


class SummaryRequest(Schema):
    kpis: KPIs
