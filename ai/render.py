"""Render only validated evidence. The LLM cannot compose new factual assertions."""


def tool_facts(name: str, data: dict) -> list[str]:
    if "notice" in data:
        return [data["notice"]]
    if name == "get_headcount":
        return [f"Active employee count: {data['total']}."] + [
            f"{d['department']}: {d['count']} employees." for d in data["departments"]
        ]
    if name == "get_attendance_summary":
        labels = {
            "present": "Present",
            "late": "Late",
            "half_day": "Half days",
            "absent": "Absent",
            "on_leave": "On leave",
            "attendance_rate": "Attendance rate (%)",
        }
        return [
            "Attendance: "
            + "; ".join(f"{label}: {data[k]}" for k, label in labels.items())
            + "."
        ]
    if name == "get_late_comers":
        rows = sorted(data["employees"], key=lambda e: e["late_count"], reverse=True)
        return [f"{e['name']}: {e['late_count']} late arrivals." for e in rows] or [
            "No late arrivals were found in this date range."
        ]
    if name == "get_leave_summary":
        return [f"{e['name']}: {e['leave_type']} leave." for e in data["employees"]] + [
            f"{k} leave count: {v}." for k, v in data["counts"].items()
        ] or ["No leave records were found in this date range."]
    if name == "get_my_leave_balance":
        return [
            f"{e['leave_type']}: quota {e['quota'] if e['quota'] is not None else 'unlimited'}, used {e['used']}, pending {e['pending']}, remaining {e['remaining'] if e['remaining'] is not None else 'unlimited'}."
            for e in data["balances"]
        ] or ["No leave balance records are available."]
    if name == "get_payroll_summary":
        return [
            f"Payroll: gross {data['total_gross']}, net {data['total_net']}, average salary {data['average_salary']}, employee count {data['employee_count']}."
        ]
    if name == "search_employees":
        return [
            f"{e['name']} ({e['employee_code']}), {e['department']}, {e['designation']}."
            for e in data["employees"]
        ] or ["No matching employees were found."]
    raise ValueError("Unknown tool")
