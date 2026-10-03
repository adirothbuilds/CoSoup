import fcntl
import pandas as pd

from stock_scanner.calendar import calendar
from stock_scanner.workflow import daily


class ExistingScanner:
    def run(self, state, rules, session, mode, research, offline=False, progress_callback=None):
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        cutoff = calendar().session_close(pd.Timestamp(session)) + pd.Timedelta(minutes=rules.settlement_minutes)
        with (state/"workflow.lock").open("a+") as f:
            # A lease recovery cannot start concurrent scanner side effects.
            fcntl.flock(f, fcntl.LOCK_EX)
            return daily(state, rules, now=cutoff, offline=offline, with_research=research,
                         register_signals=False,
                         progress_callback=progress_callback,
                         knowledge_cutoff=cutoff.isoformat() if mode == "historical_snapshot" else None)
