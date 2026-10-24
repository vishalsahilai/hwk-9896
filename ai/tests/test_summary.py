import pytest
from pydantic import ValidationError

from app.ai.exceptions import AIError
from app.ai.schemas import Selection, SummaryRequest


async def test_summary_authoritative(build, hr, backend):
    service, _ = build([Selection(fact_ids=[1, 2, 3])])
    result = await service.run("summary", SummaryRequest(kpis={"headcount": 99999}), hr)
    assert len(result.bullets) == 3 and "3" in result.bullets[0]
    assert "99999" not in str(result)


async def test_empty_company(build, hr, backend):
    backend.dashboard_data = {"headcount": 0}
    service, model = build([])
    result = await service.run("summary", SummaryRequest(kpis={}), hr)
    assert (
        len(result.bullets) == 1
        and "not enough" in result.bullets[0]
        and not model.messages
    )


async def test_invalid_selection_fallback(build, hr):
    service, _ = build([Selection(fact_ids=[999]), Selection(fact_ids=[999])])
    result = await service.run("summary", SummaryRequest(kpis={}), hr)
    assert 3 <= len(result.bullets) <= 5


async def test_summary_context(build, hr):
    service, _ = build([Selection(fact_ids=[1, 2, 3])])
    result = await service.run(
        "summary",
        SummaryRequest(
            kpis={
                "context": {
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-24",
                    "department": "Sales",
                }
            }
        ),
        hr,
    )
    assert "Sales" in result.bullets[0] and "2026-10-01" in result.bullets[0]


async def test_employee_summary_denied(build, employee):
    service, _ = build([])
    with pytest.raises(AIError) as e:
        await service.run("summary", SummaryRequest(kpis={}), employee)
    assert e.value.status_code == 403


async def test_hr_payroll_payload_denied(build, hr):
    service, _ = build([])
    with pytest.raises(AIError) as e:
        await service.run("summary", SummaryRequest(kpis={"payroll_cost": 10}), hr)
    assert e.value.status_code == 403


@pytest.mark.parametrize(
    "kpis",
    [
        {"headcount": -1},
        {"headcount": "5"},
        {"secret": 1},
        {"attendance_trend": [{"url": "secret"}]},
        {"payroll_cost": float("nan")},
    ],
)
def test_malformed_kpis(kpis):
    with pytest.raises(ValidationError):
        SummaryRequest(kpis=kpis)
