import os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import native_generation_admission_entry as module
class ImportCustody(unittest.TestCase):
 def setUp(self):
  self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
  self.root=Path(self.temporary.name)
  for name in module.REQUIRED_MODULES:
   (self.root/name).write_text('raise AssertionError("must never be imported")\n');(self.root/name).chmod(0o644)
 def observe(self,path):
  info=os.lstat(path)
  return SimpleNamespace(st_uid=0,st_mode=info.st_mode,st_nlink=info.st_nlink,st_size=info.st_size)
 def test_complete_regular_modules_pass_without_executing_them(self):
  with patch.object(Path,'lstat',autospec=True,side_effect=self.observe):module.trusted_modules(self.root)
 def test_writable_dependency_refuses_before_import(self):
  (self.root/'native_generation_reader.py').chmod(0o666)
  with patch.object(Path,'lstat',autospec=True,side_effect=self.observe),self.assertRaises(ValueError):module.trusted_modules(self.root)
 def test_ordinary_owned_dependency_refuses(self):
  def observation(path):
   info=self.observe(path)
   if path.name=='native_generation_reader.py':info.st_uid=65503
   return info
  with patch.object(Path,'lstat',autospec=True,side_effect=observation),self.assertRaises(ValueError):module.trusted_modules(self.root)
 def test_missing_dependency_refuses(self):
  (self.root/'native_generation_reader.py').unlink()
  with patch.object(Path,'lstat',autospec=True,side_effect=self.observe),self.assertRaises(ValueError):module.trusted_modules(self.root)
 def test_missing_lifecycle_peer_refuses_before_any_module_execution(self):
  (self.root/'native_lifecycle_worker_inputs.py').unlink()
  with patch.object(Path,'lstat',autospec=True,side_effect=self.observe),self.assertRaises(ValueError):module.trusted_modules(self.root)
 def test_missing_private_business_parser_refuses_before_any_module_execution(self):
  (self.root/'native_lifecycle_business_inputs.py').unlink()
  with patch.object(Path,'lstat',autospec=True,side_effect=self.observe),self.assertRaises(ValueError):module.trusted_modules(self.root)
 def test_cache_directory_refuses(self):
  (self.root/'__pycache__').mkdir()
  with patch.object(Path,'lstat',autospec=True,side_effect=self.observe),self.assertRaises(ValueError):module.trusted_modules(self.root)
 def test_linked_module_refuses(self):
  os.link(self.root/'native_generation_reader.py',self.root/'linked.py')
  with patch.object(Path,'lstat',autospec=True,side_effect=self.observe),self.assertRaises(ValueError):module.trusted_modules(self.root)
if __name__=='__main__':unittest.main()
