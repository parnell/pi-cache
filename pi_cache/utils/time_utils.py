import re
from datetime import datetime, timedelta, timezone

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta


def parse_date_string(date_string: str, reference_time: datetime | None = None) -> datetime:
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    elif reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    date_string = date_string.lower().strip()

    # Handle "now"
    if date_string == "now":
        return reference_time.astimezone(timezone.utc)

    # Handle relative patterns with more units
    match = re.match(
        r"([\d.]+)\s*(second|seconds|sec|s|minute|minutes|min|m|hour|hours|h|day|days|d|week|weeks|w|month|months|year|years|y)s?$",
        date_string,
    )
    if match:
        number, unit = match.groups()
        number = float(number)

        result_time = reference_time
        # Map units to relativedelta or timedelta arguments
        if unit in ("second", "seconds", "sec", "s"):
            result_time = reference_time + timedelta(seconds=number)
        elif unit in ("minute", "minutes", "min", "m"):
            result_time = reference_time + timedelta(minutes=number)
        elif unit in ("hour", "hours", "h"):
            result_time = reference_time + timedelta(hours=number)
        elif unit in ("day", "days", "d"):
            result_time = reference_time + timedelta(days=number)
        elif unit in ("week", "weeks", "w"):
            result_time = reference_time + timedelta(weeks=number)
        elif unit in ("month", "months"):
            result_time = reference_time + relativedelta(months=int(number))
        elif unit in ("year", "years", "y"):
            result_time = reference_time + relativedelta(years=int(number))
        return result_time.astimezone(timezone.utc)

    # Handle special cases
    special_cases = {
        "tomorrow": relativedelta(days=1),
        "next week": relativedelta(weeks=1),
        "next month": relativedelta(months=1),
        "next year": relativedelta(years=1),
    }

    if date_string in special_cases:
        return (reference_time + special_cases[date_string]).astimezone(timezone.utc)

    # Try to parse dates with timezone abbreviations
    tz_match = re.match(
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+((?:pst|pdt|est|edt|cst|cdt|mst|mdt|ast|adt|utc|gmt))$",
        date_string,
    )
    if tz_match:
        date_part, tz = tz_match.groups()
        # Map of timezone abbreviations to UTC offsets in hours
        tz_offsets = {
            "pst": -8,
            "pdt": -7,
            "mst": -7,
            "mdt": -6,
            "cst": -6,
            "cdt": -5,
            "est": -5,
            "edt": -4,
            "ast": -4,
            "adt": -3,
            "utc": 0,
            "gmt": 0,
        }

        if tz in tz_offsets:
            try:
                # Parse the date part
                local_time = datetime.strptime(date_part, "%Y-%m-%d %H:%M:%S")
                # Convert to UTC using offset
                utc_offset = timedelta(hours=tz_offsets[tz])
                utc_time = local_time - utc_offset
                return utc_time.replace(tzinfo=timezone.utc)
            except ValueError:
                pass

    # Standard parsing for everything else
    try:
        parsed_date = parse(date_string)
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
        return parsed_date.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise ValueError(f"Unable to parse the date string: {date_string}")
