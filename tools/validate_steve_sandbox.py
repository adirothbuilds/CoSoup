"""Run inside the native worker with its normal Compose security settings.

Uses the deployed adapter and official CLI tool sandbox, without a model call.
Credential tests open and close a file; they never read its contents.
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from apps.server.adapters.codex import CodexCLI, TOOL_POLICY
from apps.server.config import Settings

PROBE = '''import json,os
from pathlib import Path
result={}
paths={"auth":"/home/agent/.codex/auth.json",
       "profile_canary":"/home/agent/.codex/private-canary",
       "secrets":"/run/secrets/database_password",
       "private_data":"/var/lib/stock-scanner/private-canary",
       "host_env":"/Users/adiroth/.local/share/cosoup-dev/.env",
       "other_task":"/tmp/other-task/private-canary",
       "proc":"/proc/self/environ"}
for name,path in paths.items():
 try:
  fd=os.open(path,os.O_RDONLY);os.close(fd);result[name]="ALLOWED"
 except OSError:result[name]="DENIED"
result["task_read"]=Path("/work/inputs.json").read_text()=="synthetic input"
for name,path in {"task_write":"/work/intended-output",
                  "home_write":"/home/agent/outside-task",
                  "tmp_write":"/tmp/outside-task",
                  "runtime_write":"/usr/outside-task"}.items():
 try:Path(path).write_text("synthetic output");result[name]="ALLOWED"
 except OSError:result[name]="DENIED"
print(json.dumps(result))
'''


def verify(real_auth=False, native_session=False):
    root = Path(tempfile.mkdtemp(prefix="steve-validation-"))
    try:
        workspace = root/"task"
        workspace.mkdir()
        (workspace/"inputs.json").write_text("synthetic input")
        other = root/"other-task"
        other.mkdir()
        (other/"private-canary").write_text("synthetic private input")
        (workspace/"probe.py").write_text(PROBE.replace("/tmp/other-task/private-canary", str(other/"private-canary")))
        profile = root/"profile"
        profile.mkdir()
        (profile/"auth.json").write_text('{"auth_mode":"api_key","OPENAI_API_KEY":null}')
        (profile/"private-canary").write_text("synthetic private input")
        settings = Settings.load().model_copy(update={"codex_enabled": True, "codex_sandbox_verified": True})
        if not real_auth:
            settings = settings.model_copy(update={"codex_profile_dir": profile})
        adapter = CodexCLI(settings)
        session_home = root/"session" if native_session else None
        if session_home:
            session_home.mkdir()
            (session_home/"auth.json").touch(mode=0o600)
            (session_home/"sessions").mkdir()
            (session_home/"sessions/private-canary").write_text("synthetic session input")
            (session_home/"state_5.sqlite").write_text("synthetic state input")
            text = (workspace/"probe.py").read_text().replace('"auth":', '"session_history":"/home/agent/.codex/sessions/private-canary","session_state":"/home/agent/.codex/state_5.sqlite","auth":')
            (workspace/"probe.py").write_text(text)
        full_command = adapter.command(workspace, session_home)
        overrides = [full_command[i+1] for i, value in enumerate(full_command) if value == "-c"]
        command = full_command
        command = command[:command.index(settings.codex_binary)]
        command += [settings.codex_binary, "sandbox", "-P", "steve", "-C", "/work"]
        for override in overrides:
            command += ["-c", override]
        command += ["--", "/usr/local/bin/python", "/work/probe.py"]
        result = subprocess.run(command, env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            # No raw diagnostics from a real authentication profile.
            raise RuntimeError(f"Sandbox probe failed with exit code {result.returncode}")
        checks = json.loads(result.stdout)
        expected = {name: "DENIED" for name in ["auth", "profile_canary", "secrets", "private_data",
                                               "host_env", "other_task", "proc", "home_write", "tmp_write", "runtime_write"]}
        expected.update(task_read=True, task_write="ALLOWED")
        if native_session:
            expected.update(session_history="DENIED", session_state="DENIED")
        print(json.dumps({"profile": "dedicated" if real_auth else "synthetic", "checks": checks,
                          "passed": checks == expected}), flush=True)
        if checks != expected:
            raise RuntimeError("Sandbox isolation did not satisfy all required checks")
    finally:
        shutil.rmtree(root, ignore_errors=True)
        print(json.dumps({"scratch_cleaned": not root.exists()}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-auth", action="store_true", help="Test open access to dedicated auth without reading it")
    parser.add_argument("--native-session", action="store_true")
    args=parser.parse_args()
    verify(args.real_auth,args.native_session)
