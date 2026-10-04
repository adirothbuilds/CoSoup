import base64
import json
from pathlib import Path
import tempfile
import unittest

from apps.server.deploy.setup import SetupError, env_text, parse_env, prepare


class SetupConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def prepare(self, mode="dev", **kwargs):
        return prepare(self.root, mode, str(self.root), 501, 20, "arm64", **kwargs)

    def env(self):
        return parse_env((self.root / ".env").read_text())

    def edit(self, **changes):
        values = self.env()
        values.update(changes)
        (self.root / ".env").write_text(env_text(values))

    def test_dev_has_one_env_and_private_working_browser_configuration(self):
        result = self.prepare()
        self.assertEqual(result["origin"], "http://127.0.0.1:8081")
        self.assertEqual(self.env()["MASSIVE_API_KEY"], "")
        config = json.loads((self.root / "config/server.json").read_text())
        self.assertFalse(config["browser_secure_cookie"])
        self.assertFalse(config["codex_enabled"])
        compose = parse_env((self.root / "compose.env").read_text())
        self.assertEqual(compose["COSOUP_WEB_PLATFORM"], "linux/arm64")
        self.assertNotIn("API_TOKEN", compose)
        self.assertNotIn("MASSIVE_API_KEY", compose)
        for path in [self.root / ".env", self.root / "secrets/api_token", self.root / "config/server.json"]:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_rerun_preserves_credentials_and_existing_data(self):
        self.prepare()
        before = {path.name: path.read_bytes() for path in (self.root / "secrets").iterdir()}
        report = self.root / "data/reports/keep.md"
        report.write_text("Private test report")
        self.prepare()
        self.assertEqual(before, {path.name: path.read_bytes() for path in (self.root / "secrets").iterdir()})
        self.assertEqual(report.read_text(), "Private test report")

    def test_env_is_data_and_updates_only_the_intended_secret_and_settings(self):
        self.prepare()
        literal = 'fixture-$(touch /tmp/must-not-run) # literal'
        self.edit(MASSIVE_API_KEY=literal, LIMIT_CAPACITY_BYTES="20000000000", LIMIT_TARGET_BYTES="10000000000",
                  LIMIT_ARCHIVE_TRIGGER_BYTES="14000000000", LIMIT_ADMISSION_STOP_BYTES="18000000000")
        self.prepare()
        self.assertEqual((self.root / "secrets/massive_api_key").read_text(), literal)
        config = json.loads((self.root / "config/server.json").read_text())
        self.assertEqual(config["limits"]["capacity_bytes"], 20000000000)

    def test_prod_prepares_env_then_requires_trusted_https(self):
        with self.assertRaisesRegex(SetupError, "BROWSER_ORIGIN"):
            self.prepare("prod")
        self.assertTrue((self.root / ".env").exists())
        self.assertFalse((self.root / "config/server.json").exists())
        token = self.env()["API_TOKEN"]
        self.edit(BROWSER_ORIGIN="https://test-node.example.ts.net")
        self.prepare("prod")
        self.assertEqual(self.env()["API_TOKEN"], token)
        config = json.loads((self.root / "config/server.json").read_text())
        self.assertTrue(config["browser_secure_cookie"])

    def test_prod_rejects_http_without_materializing_services(self):
        with self.assertRaises(SetupError):
            self.prepare("prod", origin="http://127.0.0.1:8081")
        self.assertFalse((self.root / "compose.env").exists())

    def test_reusing_dev_root_for_prod_is_rejected(self):
        self.prepare()
        old = (self.root / "config/server.json").read_bytes()
        with self.assertRaisesRegex(SetupError, "MODE"):
            self.prepare("prod", origin="https://test-node.example.ts.net")
        self.assertEqual((self.root / "config/server.json").read_bytes(), old)

    def test_project_switch_cannot_reuse_existing_database_root(self):
        self.prepare()
        self.edit(COMPOSE_PROJECT_NAME="another-project")
        with self.assertRaisesRegex(SetupError, "identity"):
            self.prepare()

    def test_missing_existing_token_is_not_regenerated(self):
        self.prepare()
        token = (self.root / "secrets/api_token").read_bytes()
        self.edit(API_TOKEN="")
        with self.assertRaisesRegex(SetupError, "Missing existing credential"):
            self.prepare()
        self.assertEqual((self.root / "secrets/api_token").read_bytes(), token)

    def test_admin_and_archive_key_changes_do_not_break_existing_credentials(self):
        self.prepare()
        admin = (self.root / "secrets/admin_database_password").read_bytes()
        original_env = self.env()
        self.edit(ADMIN_DATABASE_PASSWORD="different-fixture-password")
        with self.assertRaisesRegex(SetupError, "admin password"):
            self.prepare()
        self.assertEqual((self.root / "secrets/admin_database_password").read_bytes(), admin)
        (self.root / ".env").write_text(env_text(original_env))
        key = (self.root / "secrets/archive_key").read_bytes()
        self.edit(ARCHIVE_KEY_BASE64=base64.b64encode(b"x" * 32).decode())
        with self.assertRaisesRegex(SetupError, "recoverable"):
            self.prepare()
        self.assertEqual((self.root / "secrets/archive_key").read_bytes(), key)

    def test_manual_deployment_is_preserved(self):
        config = self.root / "config/server.json"
        config.parent.mkdir()
        config.write_text('{"browser_origin":"https://existing.example"}')
        with self.assertRaisesRegex(SetupError, "manual deployment"):
            self.prepare()
        self.assertFalse((self.root / ".env").exists())

    def test_duplicate_or_malformed_env_errors_do_not_echo_values(self):
        for text in ['API_TOKEN=private-fixture\nAPI_TOKEN=second-fixture', 'API_TOKEN="private-fixture']:
            with self.assertRaises(SetupError) as caught:
                parse_env(text)
            self.assertNotIn("private-fixture", str(caught.exception))
