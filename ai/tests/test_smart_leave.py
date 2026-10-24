from datetime import date

import pytest

from app.ai.exceptions import AIError
from app.ai.schemas import LeaveProposal, LeaveRequest
from app.ai.smart_leave import anchored_dates, expected_type

from .conftest import TODAY


@pytest.mark.parametrize(
    "text,start,end",
    [
        (
            "Next Monday and Tuesday off for my sister's wedding",
            "2026-10-26",
            "2026-10-27",
        ),
        ("Mujhe kal chutti chahiye, bukhar hai.", "2026-10-25", "2026-10-25"),
        ("Day after tomorrow off", "2026-10-26", "2026-10-26"),
        ("Three days starting Monday", "2026-10-26", "2026-10-28"),
        ("This Friday off", "2026-10-30", "2026-10-30"),
        ("2026-11-03 to 2026-11-05 vacation", "2026-11-03", "2026-11-05"),
    ],
)
async def test_relative_dates(text, start, end, build, employee, backend):
    assert anchored_dates(text, TODAY) == (
        date.fromisoformat(start),
        date.fromisoformat(end),
    )
    proposal = LeaveProposal(
        leave_type=expected_type(text), start_date=start, end_date=end, reason=text
    )
    service, _ = build([proposal])
    result = await service.run("smart_leave", LeaveRequest(text=text), employee)
    assert result == proposal and not backend.calls


@pytest.mark.parametrize(
    "text,kind",
    [
        ("wedding", "casual"),
        ("fever", "sick"),
        ("vacation", "annual"),
        ("unpaid fever", "unpaid"),
        ("personal work", "casual"),
    ],
)
def test_classification(text, kind):
    assert expected_type(text) == kind


@pytest.mark.parametrize(
    "text", ["from the 3rd to the 5th", "some day off", "2026-02-30 fever"]
)
async def test_ambiguous_dates(text, build, employee):
    service, model = build([])
    with pytest.raises(AIError) as e:
        await service.run("smart_leave", LeaveRequest(text=text), employee)
    assert e.value.detail["code"] == "AI_CLARIFICATION_REQUIRED" and not model.messages


async def test_retry_bad_output(build, employee):
    good = LeaveProposal(
        leave_type="sick",
        start_date="2026-10-25",
        end_date="2026-10-25",
        reason="fever",
    )
    service, model = build([{"garbage": True}, good])
    result = await service.run(
        "smart_leave", LeaveRequest(text="Tomorrow fever"), employee
    )
    assert result == good and len(model.messages) == 2


@pytest.mark.parametrize(
    "bad",
    [
        {
            "leave_type": "invalid",
            "start_date": "2026-10-25",
            "end_date": "2026-10-25",
            "reason": "fever",
        },
        {
            "leave_type": "sick",
            "start_date": "yesterday",
            "end_date": "2026-10-25",
            "reason": "fever",
        },
        {
            "leave_type": "sick",
            "start_date": "2026-10-26",
            "end_date": "2026-10-25",
            "reason": "fever",
        },
        "not json",
    ],
)
async def test_parse_failure(bad, build, employee):
    service, model = build([bad, bad])
    with pytest.raises(AIError) as e:
        await service.run("smart_leave", LeaveRequest(text="Tomorrow fever"), employee)
    assert e.value.detail["code"] == "AI_PARSE_FAILED" and len(model.messages) == 2


async def test_sdk_json_parser_error_retries(build, employee):
    from langchain_core.exceptions import OutputParserException

    good = LeaveProposal(
        leave_type="sick",
        start_date="2026-10-25",
        end_date="2026-10-25",
        reason="fever",
    )
    service, model = build([OutputParserException("invalid JSON"), good])
    result = await service.run(
        "smart_leave", LeaveRequest(text="Tomorrow fever"), employee
    )
    assert result == good and len(model.messages) == 2


def test_explicit_named_month():
    assert anchored_dates("from the 3rd to the 5th November 2026", TODAY) == (
        date(2026, 11, 3),
        date(2026, 11, 5),
    )


async def test_disabled_leave_type(build, employee, backend):
    backend.policy_data["leave_quotas"].pop("sick")
    good = LeaveProposal(
        leave_type="sick",
        start_date="2026-10-25",
        end_date="2026-10-25",
        reason="fever",
    )
    service, _ = build([good])
    with pytest.raises(AIError) as e:
        await service.run("smart_leave", LeaveRequest(text="Tomorrow fever"), employee)
    assert e.value.detail["code"] == "AI_PARSE_FAILED"
