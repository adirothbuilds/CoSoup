import json
import signal
import threading
import time
from contextlib import nullcontext

from ..config import Settings
from ..errors import Cancelled, ServiceError
from ..persistence.database import Database
from ..services.jobs import Jobs
from ..services.storage import Storage


class Context:
    def __init__(self, jobs, job, database, settings):
        self.jobs, self.job, self.database, self.settings = jobs, job, database, settings
        self.storage = Storage(settings)
        self.stop = threading.Event()
        self.lost = threading.Event()

    def checkpoint(self, **progress):
        if self.lost.is_set():
            raise Cancelled()
        self.jobs.checkpoint(self.job.id, self.job.lease_token, progress)

    def heartbeat_loop(self):
        while not self.stop.wait(self.settings.lease_seconds/3):
            try:
                if not self.jobs.heartbeat(self.job.id, self.job.lease_token):
                    self.lost.set()
                    return
            except Exception:
                self.lost.set()
                return


def execute_one(queue, handler, database, settings):
    jobs = Jobs(database, settings)
    row = jobs.claim(queue)
    if row is None:
        return False
    context = Context(jobs, row, database, settings)
    from ..services.policy import effective
    with database.session() as db:
        context.settings = effective(settings, db)
        context.storage = Storage(context.settings)
    heartbeat = threading.Thread(target=context.heartbeat_loop, daemon=True)
    heartbeat.start()
    try:
        guard = context.storage.reader() if queue in {"scanner", "imports", "codex"} else nullcontext()
        with guard:
            result = handler(context)
        jobs.finish(row.id, row.lease_token, "succeeded", result=result)
    except Cancelled:
        jobs.finish(row.id, row.lease_token, "cancelled")
    except ServiceError as e:
        status = "waiting_for_archive" if e.code == "restore_required" else "failed"
        jobs.finish(row.id, row.lease_token, status, error={"code": e.code, "message": e.message})
    except Exception as e:
        # Raw exception strings may contain database URLs or external credentials.
        jobs.finish(row.id, row.lease_token, "failed", error={"code": "worker_error", "message": "Worker failed; inspect typed diagnostics before resuming", "type": type(e).__name__})
    finally:
        context.stop.set()
        heartbeat.join(timeout=5)
    return True


def run(queue, handler):
    settings = Settings.load()
    database = Database(settings)
    stopped = threading.Event()
    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, lambda *_: stopped.set())
    while not stopped.is_set():
        try:
            did_work = execute_one(queue, handler, database, settings)
        except Exception as e:
            print(json.dumps({"level": "error", "code": "worker_dependency_unavailable", "type": type(e).__name__}), flush=True)
            did_work = False
        if not did_work:
            stopped.wait(settings.poll_seconds)
