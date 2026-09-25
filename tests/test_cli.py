import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class CLITests(unittest.TestCase):
    def test_dry_run_and_invalid_parameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); (p/'input.md').write_text('# Results\n\nA result is reported.')
            command=[sys.executable,'-m','humanizer','rewrite',str(p/'input.md'),'--domain','Science','--output',str(p/'out'),'--no-retrieval','--dry-run']
            done=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(done.returncode,0,done.stderr)
            self.assertTrue((p/'out/report.json').exists())
            bad=subprocess.run(command+['--window-size','3'],capture_output=True,text=True)
            self.assertEqual(bad.returncode,2)
