"""Missing publication branch is distinct from a failed remote lookup."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts/resolve_publication.sh'
SHA = 'a' * 40


class PublicationRevisionTests(unittest.TestCase):
    def run_resolver(self, status=0, response='', requested=''):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'git'
            fake.write_text(f'#!{sys.executable}\nimport os,sys\nsys.stdout.write(os.environ["FAKE_RESPONSE"])\nsys.exit(int(os.environ["FAKE_STATUS"]))\n')
            fake.chmod(0o755)
            return subprocess.run(['bash', str(SCRIPT)], capture_output=True, text=True,
                                  env={**os.environ, 'PATH': tmp + os.pathsep + os.environ['PATH'],
                                       'GITHUB_REPOSITORY': 'example/babel', 'REQUESTED_PUBLICATION': requested,
                                       'FAKE_STATUS': str(status), 'FAKE_RESPONSE': response})

    def test_absent_branch_is_bootstrap_but_network_and_invalid_output_fail(self):
        self.assertEqual(self.run_resolver(2).returncode, 0)
        self.assertEqual(self.run_resolver(2).stdout, '')
        self.assertNotEqual(self.run_resolver(128).returncode, 0)
        self.assertNotEqual(self.run_resolver(0, 'invalid response').returncode, 0)
        result = self.run_resolver(0, SHA + '\trefs/heads/publication\n')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), SHA)

    def test_requested_sha_is_literal_and_never_used_as_code_or_shell_input(self):
        self.assertEqual(self.run_resolver(128, requested=SHA).stdout.strip(), SHA)
        for invalid in ['main', SHA[:12], SHA + '\nextra=value', '$(echo injected)', '../main']:
            result = self.run_resolver(0, requested=invalid)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
