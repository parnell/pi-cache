from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from pi_cache.utils.time_utils import parse_date_string


def test_relative_dates():
    before = datetime.now(ZoneInfo("UTC"))
    result = parse_date_string("2 months")
    after = datetime.now(ZoneInfo("UTC"))

    # Convert result to UTC for comparison
    result_utc = result.astimezone(ZoneInfo("UTC"))

    # Check if result is within expected range
    expected_min = before + timedelta(days=59)  # About 2 months
    expected_max = after + timedelta(days=62)  # A bit over 2 months

    assert expected_min <= result_utc <= expected_max, (
        f"Expected result between {expected_min} and {expected_max}, but got {result_utc}"
    )

    # Also check that the result is in the future
    assert result_utc > before, f"Expected result to be after {before}, but got {result_utc}"


def test_specific_date():
    result = parse_date_string("at 1/12/2025")
    # Check only the date part, ignore time and timezone
    assert result.date() == datetime(2025, 1, 12).date()


def test_invalid_input():
    with pytest.raises(ValueError):
        parse_date_string("invalid date string")


@pytest.mark.parametrize(
    "date_string, expected",
    [
        ("2023-05-17", datetime(2023, 5, 17, tzinfo=timezone.utc)),
        ("May 17, 2023", datetime(2023, 5, 17, tzinfo=timezone.utc)),
        ("3 days", lambda: (datetime.now(timezone.utc) + timedelta(days=3))),
        # Other common formats
        ("2023/05/17 14:30:00", datetime(2023, 5, 17, 14, 30, tzinfo=timezone.utc)),
        ("17.05.2023 14:30:00", datetime(2023, 5, 17, 14, 30, tzinfo=timezone.utc)),
        ("17/05/2023 2:30 PM", datetime(2023, 5, 17, 14, 30, tzinfo=timezone.utc)),
        # ISO 8601 formats
        ("2023-05-17T14:30:00Z", datetime(2023, 5, 17, 14, 30, tzinfo=timezone.utc)),
        ("2023-05-17T14:30:00+02:00", datetime(2023, 5, 17, 12, 30, tzinfo=timezone.utc)),
    ],
)
def test_various_date_formats(date_string, expected):
    result = parse_date_string(date_string)
    assert isinstance(result, datetime)
    assert result.tzinfo is not None  # Check if timezone-aware

    if callable(expected):
        expected = expected()

    # For relative time expressions, allow a small time difference
    if date_string.startswith(("in ", "next ", "last ")):
        time_difference = abs(result - expected)  # type: ignore
        assert time_difference < timedelta(seconds=1), (
            f"Failed for '{date_string}'. Expected close to {expected}, but got {result}"
        )
    else:
        # For absolute time expressions, compare without microseconds
        result = result.replace(microsecond=0)
        expected = expected.replace(microsecond=0)  # type: ignore
        assert result == expected, (
            f"Failed for '{date_string}'. Expected {expected}, but got {result}"
        )


@pytest.mark.parametrize(
    "datetime_string, expected",
    [
        ("2023-05-17 15:30:00", datetime(2023, 5, 17, 15, 30, 0, tzinfo=ZoneInfo("UTC"))),
        ("May 17, 2023 3:30 PM", datetime(2023, 5, 17, 15, 30, 0, tzinfo=ZoneInfo("UTC"))),
        ("3 hours", lambda: (datetime.now(ZoneInfo("UTC")) + timedelta(hours=3))),
        ("0.2 seconds", lambda: (datetime.now(ZoneInfo("UTC")) + timedelta(seconds=0.2))),
    ],
)
def test_various_datetime_formats(datetime_string, expected):
    result = parse_date_string(datetime_string)
    assert isinstance(result, datetime)
    assert result.tzinfo is not None  # Check if timezone-aware

    expected_datetime = expected() if callable(expected) else expected
    assert result.replace(microsecond=0) == expected_datetime.replace(  # type: ignore
        microsecond=0
    )  # Compare datetimes, ignoring microseconds


def test_timezone_awareness():
    result = parse_date_string("now")
    assert result.tzinfo is not None


def test_absolute_date():
    assert parse_date_string("2023-05-01") == datetime(2023, 5, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "date_string, reference_time, expected",
    [
        (
            "3 days",
            datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
            datetime(2023, 1, 4, 12, 0, tzinfo=timezone.utc),
        ),
        (
            "next month",
            datetime(2023, 1, 15, tzinfo=timezone.utc),
            datetime(2023, 2, 15, tzinfo=timezone.utc),
        ),
        (
            "next month",
            datetime(2023, 1, 31, tzinfo=timezone.utc),
            datetime(2023, 2, 28, tzinfo=timezone.utc),
        ),
        (
            "next year",
            datetime(2023, 12, 31, tzinfo=timezone.utc),
            datetime(2024, 12, 31, tzinfo=timezone.utc),
        ),
        (
            "2 hours",
            datetime(2023, 1, 1, 12, 30, tzinfo=timezone.utc),
            datetime(2023, 1, 1, 14, 30, tzinfo=timezone.utc),
        ),
        (
            "1 hour",
            datetime(2023, 3, 12, 1, 30, tzinfo=ZoneInfo("America/New_York")),
            datetime(2023, 3, 12, 7, 30, tzinfo=timezone.utc),
        ),
        (
            "2 days",
            datetime(2024, 2, 28, tzinfo=timezone.utc),
            datetime(2024, 3, 1, tzinfo=timezone.utc),
        ),
    ],
)
def test_parse_date_string_with_reference_time(date_string, reference_time, expected):
    result = parse_date_string(date_string, reference_time=reference_time)
    assert result == expected, f"Failed for '{date_string}' with reference time {reference_time}"


# Additional test for invalid input
@pytest.mark.parametrize(
    "invalid_date_string",
    [
        "invalid date",
        "not a real date",
        "12345",
    ],
)
def test_parse_date_string_invalid_input(invalid_date_string):
    with pytest.raises(ValueError):
        parse_date_string(invalid_date_string)


def test_date_with_time():
    assert parse_date_string("2023-05-01 15:30:00") == datetime(
        2023, 5, 1, 15, 30, tzinfo=timezone.utc
    )


def test_different_date_format():
    assert parse_date_string("May 1, 2023") == datetime(2023, 5, 1, tzinfo=timezone.utc)


def test_invalid_date_string():
    with pytest.raises(ValueError):
        parse_date_string("invalid date")


def test_date_with_timezone():
    assert parse_date_string("2023-05-01 15:30:00 PST") == datetime(
        2023, 5, 1, 23, 30, tzinfo=timezone.utc
    )


if __name__ == "__main__":
    pytest.main(["-sv", __file__])
