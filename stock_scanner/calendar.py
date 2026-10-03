from datetime import datetime, timezone

import exchange_calendars as xcals
import pandas as pd


def calendar():
    return xcals.get_calendar("XNYS")


def utc_now():
    return datetime.now(timezone.utc)


def expected_session(now=None, settlement_minutes=30):
    """Last completed NYSE session, including holidays, DST and early closes."""
    ts = pd.Timestamp(now if now is not None else utc_now())
    if ts.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    day = ts.tz_convert("America/New_York").date().isoformat()
    cal = calendar()
    session = cal.date_to_session(day, direction="previous")
    if ts < cal.session_close(session) + pd.Timedelta(minutes=settlement_minutes):
        session = cal.previous_session(session)
    return session.date().isoformat()


def sessions_ending(session, count=260):
    cal = calendar()
    index = cal.sessions.get_loc(pd.Timestamp(session))
    if count < 1 or index < count - 1:
        raise ValueError("Invalid history window")
    return [s.date().isoformat() for s in cal.sessions[index-count+1:index+1]]


def next_run(now=None, settlement_minutes=30):
    ts = pd.Timestamp(now if now is not None else utc_now())
    if ts.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    cal = calendar()
    day = ts.tz_convert("America/New_York").date().isoformat()
    session = cal.date_to_session(day, direction="next")
    ready = cal.session_close(session) + pd.Timedelta(minutes=settlement_minutes)
    if ready <= ts:
        session = cal.next_session(session)
        ready = cal.session_close(session) + pd.Timedelta(minutes=settlement_minutes)
    return {"session": session.date().isoformat(), "run_at_utc": ready.isoformat(),
            "run_at_new_york": ready.tz_convert("America/New_York").isoformat()}
