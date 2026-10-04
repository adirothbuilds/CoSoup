import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CoSoupCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        (self.bin / "cosoup").symlink_to(ROOT / "cosoup")
        self.output = self.directory / "invocation.json"
        for name in ["docker", "make"]:
            executable = self.bin / name
            executable.write_text(
                "#!/usr/bin/env python3\nimport json,os,sys\nfrom pathlib import Path\n"
                "Path(os.environ['COSOUP_TEST_OUTPUT']).write_text(json.dumps({'args':sys.argv[1:], 'cwd':os.getcwd(), 'mode':os.environ.get('MODE'), 'server_root':os.environ.get('SERVER_ROOT')}))\n"
                "sys.exit(int(os.environ.get('COSOUP_TEST_EXIT', '0')))\n"
            )
            executable.chmod(0o755)
        self.env = {key: value for key, value in os.environ.items() if not key.startswith(("COSOUP_", "COMPOSE_")) and key != "PRIVATE_ROOT"}
        self.env.update(PATH=str(self.bin) + os.pathsep + os.environ["PATH"], COSOUP_TEST_OUTPUT=str(self.output),
                        COSOUP_PRIVATE=str(self.directory / "private"), COSOUP_PROJECT="cosoup-test")

    def run_command(self, *arguments):
        return subprocess.run(["cosoup", *arguments], env=self.env, cwd=self.directory, capture_output=True, text=True)

    def test_installed_command_resolves_checkout_from_another_directory(self):
        result = self.run_command("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        invocation = json.loads(self.output.read_text())
        self.assertEqual(invocation["cwd"], str(ROOT))
        self.assertIn("status", invocation["args"])
        self.assertIn("COMPOSE_PROJECT=cosoup-test", invocation["args"])
        self.assertIn(f"PRIVATE_ROOT={self.directory / 'private'}", invocation["args"])

    def test_mac_override_reaches_compose_and_make(self):
        private = self.directory / "private"
        private.mkdir()
        override = private / "compose.macos.yaml"
        override.write_text("services: {}\n")
        result = self.run_command("compose", "logs", "--tail", "100", "api")
        self.assertEqual(result.returncode, 0, result.stderr)
        invocation = json.loads(self.output.read_text())
        self.assertIn(str(override), invocation["args"])
        self.assertEqual(invocation["args"][-4:], ["logs", "--tail", "100", "api"])
        result = self.run_command("deploy")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"COMPOSE_OVERRIDE={override}", json.loads(self.output.read_text())["args"])

    def test_missing_explicit_override_stops_before_deployment(self):
        result = self.run_command("--compose-override", str(self.directory / "absent.yaml"), "deploy")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())

    def test_child_failure_is_reported_to_the_caller(self):
        self.env["COSOUP_TEST_EXIT"] = "7"
        self.assertEqual(self.run_command("compose", "up", "-d").returncode, 7)

    def test_help_needs_no_private_configuration_or_docker(self):
        result = self.run_command("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("CoSoup", result.stdout)
        self.assertIn("compose", result.stdout)
        self.assertIn("test-e2e", result.stdout)
        self.assertFalse(self.output.exists())

    def test_managed_setup_uses_its_recorded_project_and_overlay(self):
        private = self.directory / "private"
        private.mkdir()
        (private / ".deployment.json").write_text(json.dumps({"mode": "dev", "project": "cosoup-test", "host_root": str(private)}))
        self.env.update(MODE="prod", SERVER_ROOT="/wrong-fixture-root")
        result = self.run_command("compose", "ps")
        self.assertEqual(result.returncode, 0, result.stderr)
        invocation = json.loads(self.output.read_text())
        args = invocation["args"]
        self.assertIn(str(ROOT / "apps/server/deploy/compose.setup.yaml"), args)
        self.assertIn("cosoup-test", args)
        self.assertIsNone(invocation["mode"])
        self.assertIsNone(invocation["server_root"])

    def test_command_install_is_repeatable_and_preserves_existing_files(self):
        target = self.directory / "installed"
        command = ["make", "--no-print-directory", "install-command", f"BIN_DIR={target}"]
        for _ in range(2):
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        installed = target / "cosoup"
        self.assertEqual(installed.resolve(), ROOT / "cosoup")
        installed.unlink()
        installed.write_text("Existing user command")
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(installed.read_text(), "Existing user command")
