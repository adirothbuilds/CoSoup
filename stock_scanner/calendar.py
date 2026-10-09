from datetime import datetime, timedelta, timezone
import re

import exchange_calendars as xcals
import pandas as pd


def calendar():
    return xcals.get_calendar("XNYS")


def utc_now():
    return datetime.now(timezone.utc)


def session_ready_at(session, settlement_minutes=30, data_ready_time=None):
    """Exchange settlement, optionally gated by next-calendar-day NY availability.

    The availability time is an operator policy, not a provider SLA.
    """
    close = calendar().session_close(session)
    ready = close + pd.Timedelta(minutes=settlement_minutes)
    if data_ready_time is not None:
        if not isinstance(data_ready_time, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", data_ready_time):
            raise ValueError("Data readiness time must be HH:MM in New York")
        day = close.tz_convert("America/New_York").date() + timedelta(days=1)
        # Reject ambiguous/nonexistent local times rather than silently shifting.
        available = pd.Timestamp(f"{day.isoformat()} {data_ready_time}").tz_localize("America/New_York")
        ready = max(ready, available.tz_convert("UTC"))
    return ready


def expected_session(now=None, settlement_minutes=30, data_ready_time=None):
    """Last eligible NYSE session, including optional provider availability."""
    ts = pd.Timestamp(now if now is not None else utc_now())
    if ts.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    day = ts.tz_convert("America/New_York").date().isoformat()
    cal = calendar()
    session = cal.date_to_session(day, direction="previous")
    while ts < session_ready_at(session, settlement_minutes, data_ready_time):
        session = cal.previous_session(session)
    return session.date().isoformat()


def sessions_ending(session, count=260):
    cal = calendar()
    index = cal.sessions.get_loc(pd.Timestamp(session))
    if count < 1 or index < count - 1:
        raise ValueError("Invalid history window")
    return [s.date().isoformat() for s in cal.sessions[index-count+1:index+1]]


def next_run(now=None, settlement_minutes=30, data_ready_time=None):
    ts = pd.Timestamp(now if now is not None else utc_now())
    if ts.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    cal = calendar()
    # Yesterday's close can still be waiting for next-day provider availability.
    session = cal.next_session(pd.Timestamp(expected_session(ts, settlement_minutes, data_ready_time)))
    ready = session_ready_at(session, settlement_minutes, data_ready_time)
    while ready <= ts:
        session = cal.next_session(session)
        ready = session_ready_at(session, settlement_minutes, data_ready_time)
    return {"session": session.date().isoformat(), "run_at_utc": ready.isoformat(),
            "run_at_new_york": ready.tz_convert("America/New_York").isoformat(),
            "market_close_at_utc": cal.session_close(session).isoformat(),
            "data_ready_time_new_york": data_ready_time}
