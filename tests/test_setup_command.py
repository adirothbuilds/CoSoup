import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SetupCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        self.private = self.directory / "private data"
        self.calls = self.directory / "calls.jsonl"
        self.env = os.environ.copy()
        self.env.update(PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        COSOUP_TEST_ROOT=str(ROOT), COSOUP_TEST_CALLS=str(self.calls),
                        COSOUP_TEST_OS="Darwin", COSOUP_TEST_ARCH="arm64",
                        COSOUP_TEST_PRIVATE=str(self.private), MASSIVE_API_KEY="ambient-fixture-not-for-deployment")
        self.env.pop("DOCKER_HOST", None)
        for name in ["uname", "id", "docker", "open", "pbcopy", "curl"]:
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''
                import json,os,sys,shutil
                from pathlib import Path
                tool=Path(sys.argv[0]).name
                args=sys.argv[1:]
                if tool=='uname':
                    print(os.environ['COSOUP_TEST_OS'] if args==['-s'] else os.environ['COSOUP_TEST_ARCH'])
                elif tool=='id':
                    print('501' if args==['-u'] else '20')
                else:
                    with open(os.environ['COSOUP_TEST_CALLS'],'a') as out:
                        out.write(json.dumps({'tool':tool,'args':args,'cwd':os.getcwd()})+'\\n')
                    if tool=='curl':
                        shutil.copyfile(os.environ['COSOUP_TEST_ARCHIVE'],args[args.index('-o')+1])
                    if tool=='docker':
                        if args[:2]==['context','inspect']:
                            print(os.environ.get('COSOUP_TEST_ENDPOINT','unix:///fixture.sock'))
                        elif args[:1]==['info']:
                            print('Docker Desktop')
                        elif args[:1]==['run']:
                            sys.path.insert(0,os.environ['COSOUP_TEST_ROOT'])
                            from apps.server.deploy.setup import prepare
                            get=lambda flag:args[args.index(flag)+1]
                            prepare(os.environ['COSOUP_TEST_PRIVATE'],get('--mode'),get('--host-root'),501,20,
                                    get('--architecture'),get('--origin') if '--origin' in args else None)
                        elif args[:1]==['compose']:
                            if args[-2:]==['ps','-aq'] and os.environ.get('COSOUP_TEST_COLLISION'):
                                print('fixture-container')
                            if 'migrate' in args and os.environ.get('COSOUP_TEST_MIGRATION_FAILURE'):
                                sys.exit(9)
                        elif args[:1]==['inspect']:
                            print('/another/private/root')
            '''))
            path.chmod(0o755)

    def setup(self, *args):
        return subprocess.run(['bash', str(ROOT / 'setup.sh'), '--root', str(self.private), *args],
                              cwd=self.directory, env=self.env, capture_output=True, text=True)

    def invocations(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def test_mac_default_bootstraps_without_host_packages_and_waits_for_services(self):
        result = self.setup('--no-open')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.invocations()
        bootstrap = next(call['args'] for call in calls if call['args'][:1]==['build'])
        self.assertIn('linux/amd64', bootstrap)
        ups = [call['args'] for call in calls if call['tool']=='docker' and call['args'][:1]==['compose'] and 'up' in call['args']]
        self.assertEqual(len(ups), 2)
        self.assertTrue(all('--wait' in args for args in ups))
        self.assertNotIn('codex-worker', ups[-1])
        self.assertIn('http://127.0.0.1:8081', result.stdout)
        self.assertNotIn('ambient-fixture-not-for-deployment', (self.private / '.env').read_text())
        self.assertNotIn('ambient-fixture-not-for-deployment', result.stdout)
        self.assertFalse(any(call['tool']=='open' for call in calls))

    def test_linux_defaults_to_prod_and_records_the_given_https_origin(self):
        self.env.update(COSOUP_TEST_OS='Linux', COSOUP_TEST_ARCH='x86_64')
        result = self.setup('--origin', 'https://fixture-node.example.ts.net')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.private / '.deployment.json').read_text())['mode'], 'prod')
        self.assertIn('https://fixture-node.example.ts.net', result.stdout)

    def test_failed_migration_does_not_start_application_workers(self):
        self.env['COSOUP_TEST_MIGRATION_FAILURE']='1'
        result = self.setup('--no-open')
        self.assertEqual(result.returncode, 9)
        self.assertFalse(any('scanner-worker' in call['args'] for call in self.invocations()))
        self.assertFalse((self.private / '.setup-lock').exists())

    def test_project_collision_stops_before_replacing_other_services(self):
        self.env['COSOUP_TEST_COLLISION']='1'
        result = self.setup('--no-open')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('another private root', result.stderr)
        self.assertFalse(any('up' in call['args'] for call in self.invocations()))

    def test_remote_context_is_rejected_before_creating_private_files(self):
        self.env['COSOUP_TEST_ENDPOINT']='ssh://remote-fixture'
        result = self.setup('--no-open')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.private.exists())

    def test_status_does_not_build_or_change_credentials(self):
        self.assertEqual(self.setup('--no-open').returncode, 0)
        before = (self.private / '.env').read_bytes()
        self.calls.unlink()
        result = self.setup('--action', 'status')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(call['args'][:1] in [['build'],['run']] for call in self.invocations()))
        self.assertEqual((self.private / '.env').read_bytes(), before)

    def test_streamed_bootstrap_downloads_selected_ref_and_delegates_to_that_checkout(self):
        archive = self.directory / 'fixture.tar.gz'
        with tarfile.open(archive,'w:gz') as output:
            for name in ['setup.sh','apps/server/deploy/setup.py','apps/server/deploy/compose.yaml',
                         'apps/server/deploy/compose.setup.yaml','apps/web/deploy/compose.yaml']:
                output.add(ROOT / name, arcname='fixture-repo/' + name)
        self.env.update(COSOUP_TEST_ARCHIVE=str(archive), COSOUP_SOURCE_PARENT=str(self.directory / 'downloaded'))
        result = subprocess.run(['bash','-s','--','--mode','dev','--root',str(self.private),
                                 '--ref','fixture-commit','--no-open'], input=(ROOT/'setup.sh').read_text(),
                                cwd=self.directory, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.invocations()
        download = next(call for call in calls if call['tool']=='curl')
        self.assertIn('https://codeload.github.com/adirothbuilds/CoSoup/tar.gz/fixture-commit',download['args'])
        build = next(call for call in calls if call['tool']=='docker' and call['args'][:1]==['build'])
        self.assertTrue(Path(build['cwd']).is_relative_to(self.directory/'downloaded'))

    def test_mac_opens_browser_and_copies_token_only_when_requested(self):
        result = self.setup('--copy-token')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.invocations()
        self.assertTrue(any(call['tool']=='open' and call['args']==['http://127.0.0.1:8081'] for call in calls))
        self.assertTrue(any(call['tool']=='pbcopy' for call in calls))
