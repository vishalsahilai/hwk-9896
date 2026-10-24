import re
from calendar import month_name
from datetime import date, timedelta

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from .exceptions import AIError
from .prompts import LEAVE
from .schemas import LeaveProposal

WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def anchored_dates(text: str, today: date):
    """Resolve unambiguous anchors; never guess a missing month/year."""
    low = text.casefold()
    iso = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if iso:
        values = [date.fromisoformat(s) for s in iso]
        if len(values) > 2:
            raise ValueError("Too many dates")
        return values[0], values[-1]
    month_pattern = "|".join(month_name[1:]).casefold()
    named = re.search(
        r"(?:from\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:to\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+)?("
        + month_pattern
        + r")\s+(\d{4})",
        low,
    )
    if named:
        day, last, month, year = named.groups()
        m = [x.casefold() for x in month_name].index(month)
        return date(int(year), m, int(day)), date(int(year), m, int(last or day))
    if "day after tomorrow" in low:
        start = today + timedelta(days=2)
    elif "tomorrow" in low or re.search(r"\bkal\b", low):
        start = today + timedelta(days=1)
    elif "today" in low or re.search(r"\baaj\b", low):
        start = today
    else:
        matches = list(re.finditer("|".join(WEEKDAYS), low))
        if not matches:
            raise ValueError("Please specify dates including month and year")
        first = WEEKDAYS.index(matches[0].group())
        offset = (first - today.weekday()) % 7
        if offset == 0:
            offset = 7
        start = today + timedelta(days=offset)
        if len(matches) > 2:
            raise ValueError("Ambiguous date range")
        if len(matches) == 2:
            end = start + timedelta(
                days=(WEEKDAYS.index(matches[1].group()) - first) % 7
            )
            return start, end
    duration = re.search(r"(?:for\s+)?(\d+|one|two|three|four|five)\s+days?", low)
    n = 1
    if duration:
        raw = duration.group(1)
        n = (
            int(raw)
            if raw.isdigit()
            else ["one", "two", "three", "four", "five"].index(raw) + 1
        )
        if not 1 <= n <= 366:
            raise ValueError("Invalid duration")
    return start, start + timedelta(days=n - 1)


def expected_type(text):
    low = text.casefold()
    if "unpaid" in low:
        return "unpaid"
    if any(
        w in low for w in ("fever", "illness", "sick", "doctor", "hospital", "bukhar")
    ):
        return "sick"
    if any(w in low for w in ("vacation", "holiday trip")):
        return "annual"
    return "casual"


async def propose(request, manager, today, deadline, attempts):
    try:
        start, end = anchored_dates(request.text, today)
    except ValueError:
        raise AIError(
            "AI_CLARIFICATION_REQUIRED",
            "Please specify unambiguous dates, including month and year where needed.",
            422,
        ) from None
    messages = [
        SystemMessage(
            content=LEAVE
            + f"\nToday: {today.isoformat()} ({today.strftime('%A')}). Verified date anchors: {start} to {end}."
        ),
        HumanMessage(content=request.text),
    ]
    for _ in range(2):
        try:
            proposal = await manager.invoke(
                messages, deadline, attempts, schema=LeaveProposal
            )
            if (proposal.start_date, proposal.end_date) != (start, end):
                raise ValueError("Date anchors differ")
            if proposal.leave_type != expected_type(request.text):
                raise ValueError("Leave classification differs")
            if proposal.reason.casefold() not in request.text.casefold():
                raise ValueError("Reason must quote user text")
            return proposal
        except (ValidationError, OutputParserException, ValueError):
            messages.append(
                HumanMessage(
                    content="Invalid proposal. Use verified dates, correct leave type, and an exact excerpt of the request as reason."
                )
            )
    raise AIError(
        "AI_PARSE_FAILED",
        "The assistant could not understand the request. Please use the normal form.",
        422,
    )
