import json
import signal
import threading

from ...config import Settings
from ...persistence.database import Database
from .service import tick

settings, stopped = Settings.load(), threading.Event()
database = Database(settings)
for s in (signal.SIGTERM, signal.SIGINT):
    signal.signal(s, lambda *_: stopped.set())
while not stopped.is_set():
    try:
        tick(database, settings)
    except Exception as e:
        print(json.dumps({"code": "scheduler_dependency_failure", "type": type(e).__name__}), flush=True)
    stopped.wait(settings.poll_seconds)
