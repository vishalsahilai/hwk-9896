from .exceptions import AIError
from .graph import select_facts
from .schemas import KPIs, SummaryResponse

LABELS = {
    "headcount": "Active employee count",
    "present_today": "Employees present today",
    "on_leave_today": "Employees on leave today",
    "late_today": "Employees late today",
    "pending_approvals": "Requests awaiting approval",
    "attrition_ytd": "Attrition YTD",
    "payroll_cost": "Payroll cost",
    "avg_salary": "Average salary",
}


async def summarize(request, user, backend, manager, deadline, attempts):
    if user.role not in {"admin", "hr"}:
        raise AIError(
            "AI_FORBIDDEN", "Dashboard summaries are available to Admin and HR.", 403
        )
    if user.role == "hr" and any(
        getattr(request.kpis, k) is not None
        for k in ("payroll_cost", "avg_salary", "attrition_ytd")
    ):
        raise AIError(
            "AI_FORBIDDEN", "This dashboard scope is restricted to Admin.", 403
        )
    # Client values are a display hint only. All model evidence comes from the server.
    data = KPIs.model_validate(await backend.dashboard(user, request.kpis.context))
    if data.headcount == 0 or not any(getattr(data, k) for k in LABELS):
        return SummaryResponse(
            bullets=["There is not enough company data yet to summarize."]
        )
    allowed = (
        LABELS
        if user.role == "admin"
        else {
            k: v
            for k, v in LABELS.items()
            if k not in {"payroll_cost", "avg_salary", "attrition_ytd"}
        }
    )
    context = request.kpis.context.model_dump(mode="json", exclude_none=True)
    suffix = f" (filters: {context})" if context else ""
    facts = [
        f"{label}: {getattr(data, k)}{suffix}."
        for k, label in allowed.items()
        if getattr(data, k) is not None
    ]
    facts += [
        f"Department {row.department}: {row.count} employees{suffix}."
        for row in data.headcount_by_dept
    ]
    if len(facts) < 3:
        return SummaryResponse(
            bullets=["There is not enough company data yet to summarize."]
        )
    chosen = await select_facts(
        manager,
        "Select three to five useful dashboard insights.",
        facts,
        deadline,
        attempts,
    )
    if len(chosen) < 3:
        chosen = facts[:5]
    return SummaryResponse(bullets=chosen)
