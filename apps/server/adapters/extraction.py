import json
import os
import subprocess
import sys
from pathlib import Path

from ..errors import Cancelled, ServiceError


class LocalExtractor:
    """Fixed parser command with bounded output, runtime and a minimal environment."""
    def __init__(self, settings):
        self.settings = settings

    def extract(self, source, media_type, workspace=None, checkpoint=None):
        workspace = Path(workspace or source.parent)
        output = workspace/"proposal.json"
        command = [sys.executable, "-m", "apps.server.workers.imports.parser", str(source), media_type,
                   str(output), json.dumps(self.settings.limits.model_dump()), self.settings.timezone]
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(Path(__file__).resolve().parents[3]),
               "TMPDIR": str(workspace)}
        process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import time
        start = time.monotonic()
        try:
            while process.poll() is None:
                if time.monotonic()-start > self.settings.limits.task_timeout_seconds:
                    raise ServiceError("import_timeout", "Document extraction exceeded configured timeout")
                if checkpoint:
                    checkpoint(stage="extracting_document")
                time.sleep(.2)
            if process.returncode != 0 or not output.is_file() or output.stat().st_size > self.settings.limits.task_output_bytes:
                raise ServiceError("import_parse_failed", "Document extraction failed or exceeded limits; original upload is retained")
            return json.loads(output.read_text())
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
