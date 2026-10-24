from datetime import datetime, time, timedelta
from typing import Annotated

from pydantic import Field

from .schemas import Count, Name, Schema


class Policy(Schema):
    office_start: time = time(9)
    grace_minutes: int = Field(15, ge=0, le=240)
    half_day_hours: float = Field(5, gt=0, le=24)
    weekend_days: list[Annotated[int, Field(ge=0, le=6)]] = Field(
        default_factory=lambda: [5, 6], max_length=7
    )
    leave_quotas: dict[Name, Count | None] = Field(
        default_factory=lambda: {"annual": 14, "sick": 8, "casual": 10, "unpaid": None},
        max_length=20,
    )

    def facts(self) -> list[str]:
        late = (
            datetime.combine(datetime(2000, 1, 1), self.office_start)
            + timedelta(minutes=self.grace_minutes)
        ).strftime("%H:%M")
        weekdays = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        weekends = ", ".join(weekdays[d] for d in self.weekend_days if 0 <= d <= 6)
        return [
            f"Office starts at {self.office_start.strftime('%H:%M')}; grace is {self.grace_minutes} minutes; late after {late}.",
            f"Half day means fewer than {self.half_day_hours:g} hours worked. Weekends: {weekends}.",
            "Leave quotas: "
            + "; ".join(
                f"{k}: {'unlimited' if v is None else str(v) + ' days'}"
                for k, v in self.leave_quotas.items()
            )
            + ".",
            "Leave counts working days only, excluding weekends and holidays. Overlaps and insufficient balances are rejected.",
            "Gross salary is 1.5 times basic: HRA is 40% and medical is 10% of basic.",
            "Deductions use absent days, unpaid leave and half of each half day; joiners and leavers are prorated by working days.",
            "HR prepares payroll drafts. Admin finalizes payroll. Finalized runs cannot be edited.",
            "Attendance corrections require a request and HR approval; employees cannot directly edit attendance.",
            "Illustrative annual tax: up to 600000: zero; up to 1200000: 5% above 600000; up to 2400000: 30000 + 15% above 1200000; up to 3600000: 210000 + 25% above 2400000; above: 510000 + 35% above 3600000. Monthly tax is annual tax divided by 12.",
        ]
