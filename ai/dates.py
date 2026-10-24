from calendar import monthrange
from datetime import date, timedelta

from .exceptions import AIError


def date_range(args: dict, today: date) -> dict:
    args = args.copy()
    period = args.pop("period", None)
    start, end = args.get("start_date"), args.get("end_date")
    if period and (start or end):
        raise AIError(
            "AI_INVALID_DATES", "Use dates or a relative period, not both.", 422
        )
    if period:
        if period == "today":
            start = end = today
        elif period == "yesterday":
            start = end = today - timedelta(days=1)
        elif period in {"this week", "last week"}:
            start = today - timedelta(
                days=today.weekday() + (7 if period == "last week" else 0)
            )
            end = start + timedelta(days=6)
        else:
            anchor = today.replace(day=1)
            if period == "last month":
                anchor -= timedelta(days=1)
            start = anchor.replace(day=1)
            end = anchor.replace(day=monthrange(anchor.year, anchor.month)[1])
    if not start or not end or end < start or (end - start).days > 366:
        raise AIError(
            "AI_INVALID_DATES",
            "Please specify a valid date range of at most one year.",
            422,
        )
    args.update(start_date=start, end_date=end)
    return args
