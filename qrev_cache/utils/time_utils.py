from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import dateparser
import pytest
from dateparser.conf import Settings


def parse_date_string(date_string: str, reference_time: datetime | None = None) -> datetime:
    settings = Settings()
    settings.TIMEZONE = "UTC"  # type: ignore
    settings.RETURN_TIME_AS_PERIOD = False  # type: ignore
    settings.PREFER_DATES_FROM = "future"  # type: ignore

    original_tz = None
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    else:
        # Store the original timezone
        original_tz = reference_time.tzinfo
        # Ensure reference_time is timezone-aware
        reference_time = reference_time.astimezone(timezone.utc)

    settings.RELATIVE_BASE = reference_time  # type: ignore

    parsed_date = dateparser.parse(date_string, settings=settings)  # type: ignore
    if parsed_date is None:
        raise ValueError(f"Unable to parse the date string: {date_string}")

    # Ensure the result is timezone-aware
    if parsed_date.tzinfo is None:
        parsed_date = parsed_date.replace(tzinfo=timezone.utc)
    else:
        parsed_date = parsed_date.astimezone(timezone.utc)

    # For certain relative date strings, set time to midnight in the original timezone
    if date_string.lower() in ["tomorrow", "next week"]:
        if original_tz:
            parsed_date = parsed_date.astimezone(original_tz)
            parsed_date = parsed_date.replace(hour=0, minute=0, second=0, microsecond=0)
            parsed_date = parsed_date.astimezone(timezone.utc)
        else:
            parsed_date = parsed_date.replace(hour=0, minute=0, second=0, microsecond=0)

    return parsed_date
