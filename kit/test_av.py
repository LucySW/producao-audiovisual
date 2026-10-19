import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('av',Path(__file__).with_name('av.py'))
av=importlib.util.module_from_spec(spec);spec.loader.exec_module(av)

class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        (self.root/'docs').mkdir();(self.root/'docs/a.md').write_text('before')
        av.init(self.root,['docs']);self.folder=self.root/'.continuidade'
    def tearDown(self):self.tmp.cleanup()
    def test_changes_survive_repeated_scan_without_checkpoint(self):
        (self.root/'docs/a.md').write_text('after')
        av.scan(self.root);av.scan(self.root)
        self.assertEqual(av.read(self.folder/'delta.json')['changes']['changed'],['docs/a.md'])
    def test_interrupted_and_unknown_operation_remain_pending(self):
        av.event(self.folder,'begin',operation='paid',summary='pending generation')
        av.scan(self.root)
        self.assertEqual(len(av.read(self.folder/'delta.json')['pending']),1)
        av.event(self.folder,'end',operation='paid',result='unknown');av.scan(self.root)
        self.assertEqual(len(av.read(self.folder/'delta.json')['pending']),1)
        av.event(self.folder,'end',operation='paid',result='verified');av.scan(self.root)
        self.assertEqual(av.read(self.folder/'delta.json')['pending'],[])
    def test_removed_file_is_reported_without_deleting_other_files(self):
        (self.root/'docs/a.md').unlink();(self.root/'docs/b.md').write_text('new')
        av.scan(self.root);d=av.read(self.folder/'delta.json')['changes']
        self.assertEqual(d['removed'],['docs/a.md']);self.assertEqual(d['added'],['docs/b.md'])
    def test_hook_does_not_store_prompt_or_command_secret(self):
        payload={'hook_event_name':'PreToolUse','session_id':'s','tool_use_id':'t','tool_name':'Bash','tool_input':{'command':'secret-password'},'prompt':'private prompt'}
        with patch('sys.stdin',io.StringIO(json.dumps(payload))):av.hook(self.root)
        saved=''.join(p.read_text() for p in (self.folder/'events').glob('*.json'))
        self.assertNotIn('secret-password',saved);self.assertNotIn('private prompt',saved)
    def test_hook_install_preserves_other_settings_and_is_idempotent(self):
        av.atomic(self.root/'.claude/settings.local.json',{'permissions':{'deny':['secret']},'hooks':{'Stop':[{'hooks':[{'type':'command','command':'echo old'}]}]}})
        av.hooks(self.root);av.hooks(self.root)
        s=av.read(self.root/'.claude/settings.local.json')
        self.assertEqual(s['permissions']['deny'],['secret']);self.assertEqual(len(s['hooks']['Stop']),2)
    def test_lock_prevents_competing_writer_and_releases(self):
        with av.lock(self.folder):
            with self.assertRaises(RuntimeError):
                with av.lock(self.folder):pass
        with av.lock(self.folder):pass
    def test_reinitialize_refused(self):
        with self.assertRaises(ValueError):av.init(self.root,['docs'])
    def test_watch_outside_root_refused(self):
        with self.assertRaises(ValueError):av.inventory(self.root,{'watch':['..']},{})

if __name__=='__main__':unittest.main()
