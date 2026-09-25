import tempfile
import unittest
from pathlib import Path
from humanizer.config import load_config, ConfigurationError

class ConfigTests(unittest.TestCase):
    def test_env_is_data_and_environment_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'.env').write_text('DEEPSEEK_API_KEY="test-secret" # comment\nDEEPSEEK_MODEL=deepseek-flash\nIGNORED=$(touch owned)\n')
            c=load_config(root, {'DEEPSEEK_MODEL':'deepseek-v4-pro'})
            self.assertEqual(c['api_key'],'test-secret'); self.assertEqual(c['models']['default'],'deepseek-v4-pro')
            self.assertNotIn('IGNORED',c); self.assertFalse((root/'owned').exists())
            with self.assertRaises(ConfigurationError): load_config(root,{'DEEPSEEK_BASE_URL':'https://evil.example'})
    def test_dry_run_needs_no_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_config(Path(tmp),{},False)['api_key'],'')
            with self.assertRaises(ConfigurationError): load_config(Path(tmp),{})
