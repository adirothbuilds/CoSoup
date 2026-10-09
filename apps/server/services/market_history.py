"""Durable, entitlement-bounded missing-only history acquisition."""
import fcntl
from datetime import datetime, timezone

import pandas as pd

from stock_scanner.calendar import calendar, expected_session
from stock_scanner.provider import Client, ProviderError, ensure_grouped, splits

from ..errors import ServiceError


def plan_history(storage, settings, at=None):
    at = pd.Timestamp(at or datetime.now(timezone.utc))
    if at.tzinfo is None:
        raise ServiceError('invalid_timestamp', 'History planning requires a timezone', 422)
    # Calendar years, not 520 trading sessions: the latter can exceed entitlement.
    first = (at.tz_convert('America/New_York').normalize() - pd.DateOffset(years=2)).date().isoformat()
    end = expected_session(at, settings.settlement_minutes, settings.market_data_ready_time)
    sessions = [s.date().isoformat() for s in calendar().sessions_in_range(first, end)]
    missing = [s for s in sessions if not storage.path('market/raw/grouped/'+s+'.json.gz').is_file()]
    return {'first_session': sessions[0], 'last_session': sessions[-1], 'sessions': sessions,
            'missing_sessions': missing, 'required_sessions': len(sessions),
            'estimated_minimum_grouped_requests': len(missing), 'years': 2,
            'note': 'Two calendar years within current entitlement; dated split references add requests. Original cache files are retained as time advances.'}


def acquire(context):
    job, storage = context.job, context.storage
    with context.database.session() as db:
        storage.reserve(db, job.id, job.owner_id, context.settings.limits.scan_reservation_bytes)
    target = job.payload.get('history_plan') or plan_history(storage, context.settings)
    # Only trusted persisted plans may choose the bounded acquisition dates.
    sessions = target['sessions']
    root = storage.path('market'); root.mkdir(parents=True, exist_ok=True)
    client = Client(root)
    total = len(sessions)
    def checkpoint(**extra):
        cached = sum((root/'raw/grouped'/(s+'.json.gz')).is_file() for s in sessions)
        context.checkpoint(first_session=sessions[0], last_session=sessions[-1],
                           total_sessions=total, cached_sessions=cached, missing_sessions=total-cached, **extra)
    with (root/'workflow.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            # Recent missing history first; an oldest-date entitlement rejection
            # still leaves all successfully collected sessions available.
            for session in reversed(sessions):
                checkpoint(current_session=session, stage='history_acquisition')
                ensure_grouped(client, [session], progress=lambda *a, **kw: None)
                with context.database.session() as db:
                    storage.register(db, job.owner_id, root/'raw/grouped'/(session+'.json.gz'), 'grouped', {'session':session})
            checkpoint(stage='split_reference')
            splits(client, sessions[0], sessions[-1])
            with context.database.session() as db:
                storage.register(db, job.owner_id, root/'raw/splits'/(sessions[0]+'_'+sessions[-1]+'.json.gz'), 'reference', {'session':sessions[-1]})
        except ProviderError as error:
            checkpoint(stage='blocked', source_errors=[error.as_dict()])
            raise ServiceError('history_source_blocked', 'History source rejected acquisition; exact error saved in progress, no automatic retry') from None
    checkpoint(stage='complete')
    return {'first_session':sessions[0], 'last_session':sessions[-1], 'cached_sessions':total,
            'years':2, 'retention':'Previously acquired raw sessions remain retained; daily scans append missing sessions.'}
