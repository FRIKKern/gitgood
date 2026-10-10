import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
import uuid

from native_enrollment_inputs import NativeEnrollmentInputs, bootstrap_digest
from native_inventory import EXECUTABLES, directory_identity
from retirement_snapshot import retained_file_identity
from upgrade_journal import canonical, UpgradeRefused
from enrollment_journal import EnrollmentRefused


@unittest.skipUnless(sys.platform == "linux", "Private native enrollment input files require Linux")
class EnrollmentInputCustodyTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name);self.base.chmod(0o700)
        self.root = self.base / "installation";self.root.mkdir(mode=0o700)
        self.directory = self.base / "inputs";self.directory.mkdir(mode=0o700)
        for name in ["configuration", "storage", "ssh-host", "history", "staging"]:
            (self.root / name).mkdir(mode=0o700)
        self.archive = self.base / "inert-archive";self.archive.write_bytes(b"Not a native archive; no inspection or execution is proved here.");self.archive.chmod(0o600)
        self.installation = str(uuid.uuid4())
        resources = {name:directory_identity(self.root if name == "root" else self.root / name,private=True) for name in ["root","configuration","storage","ssh-host"]}
        binaries = {name:{"path":"/unexecuted/"+name,"device":1,"inode":2,"uid":os.getuid(),"bytes":3,"sha256":"a"*64} for name in EXECUTABLES}
        groups = {name:{"path":"/unobserved/"+name,"kernel_path":"/unobserved/"+name,"device":1,"inode":2,"delegated_uid":os.getuid()} for name in ["native","web","edge","maintenance","driver"]}
        bindings={"protocol":1,"installation":self.installation,"host":"inert-component-host","uid":os.getuid(),"platform":"linux-x86_64","resources":resources,"configuration_sha256":{},"ssh_host_key_sha256":{},"executables":binaries,"cgroups":groups,
                  "database":{"cluster":"123","database":"unobserved","database_oid":1,"owner_oid":2,"role_oid":2,"encoding":"UTF8","version":"18.4","address":"127.0.0.1","port":55432}}
        self.allocation={"protocol":1,"purpose":"native_initial_allocation","profile":"ubuntu-24.04-linux-x86_64","installation":self.installation,"bindings":bindings,"bindings_sha256":hashlib.sha256(canonical(bindings)).hexdigest(),
                         "scope":{"boot_id":str(uuid.uuid4()),"mount_namespace":"mnt:[123]","cgroup_namespace":"cgroup:[456]"},"empty_directories":{name:directory_identity(self.root/name,private=True) for name in ["storage","history","staging"]},
                         "empty_database":{"relations":0,"functions":0,"types":0,"schemas":0,"extensions":0,"public_writable":True}}
        bootstrap={"installation":self.installation,"request":str(uuid.uuid4()),"username":"initial-owner","team":"initial-team","password":"private-inert-fixture-password"}
        self.inputs={"protocol":1,"bootstrap":bootstrap,"plan":{"archive":retained_file_identity(self.archive),"bootstrap_request_sha256":bootstrap_digest(bootstrap)}}
        self.request={"protocol":1,"purpose":"native_initial_enrollment","operation":str(uuid.uuid4()),"intent":{"installation":self.installation,"candidate":"a"*40,"artifact_sha256":self.inputs["plan"]["archive"]["sha256"],"allocation_sha256":"","inputs_sha256":""}}
        adapter=patch("native_enrollment_inputs.supported_platform",return_value="ubuntu-24.04-linux-x86_64");adapter.start();self.addCleanup(adapter.stop)
        self.save()

    def save(self):
        self.allocation["bindings_sha256"]=hashlib.sha256(canonical(self.allocation["bindings"])).hexdigest()
        self.request["intent"]["allocation_sha256"]=hashlib.sha256(canonical(self.allocation)).hexdigest()
        self.request["intent"]["inputs_sha256"]=hashlib.sha256(canonical(self.inputs)).hexdigest()
        self.digest=hashlib.sha256(canonical(self.request)).hexdigest()
        for name,value in [("request",self.request),("allocation",self.allocation),("inputs",self.inputs)]:
            path=self.directory/(name+".json");path.write_bytes(canonical(value)+b"\n");path.chmod(0o600)

    def value(self):return NativeEnrollmentInputs(self.directory,self.digest)

    def unchanged_installation(self):
        self.assertEqual({p.name for p in self.root.iterdir()},{"configuration","storage","ssh-host","history","staging"})
        self.assertFalse(any(p.is_file() for p in self.root.rglob("*")))

    def test_sealed_inputs_are_read_only_and_never_claim_responsibility_or_execute(self):
        before={p.name:(p.stat().st_ino,p.read_bytes()) for p in self.directory.iterdir()}
        with patch("subprocess.run") as run:
            value=self.value();value.observe_inputs()
        run.assert_not_called()
        self.assertEqual(value.intent["installation"],self.installation)
        self.assertNotIn(self.inputs["bootstrap"]["password"],repr(value))
        self.assertEqual({p.name:(p.stat().st_ino,p.read_bytes()) for p in self.directory.iterdir()},before)
        self.unchanged_installation()

    def test_wrong_digest_or_resealed_commands_roles_and_nested_fields_refuse(self):
        with self.assertRaises(EnrollmentRefused):NativeEnrollmentInputs(self.directory,"wrong-digest")
        with self.assertRaises(UpgradeRefused):NativeEnrollmentInputs(self.directory,"0"*64)
        for mapping,key,value in [(self.request,"command","never-execute"),(self.inputs,"callback","never-execute"),(self.inputs["bootstrap"],"role","owner"),(self.inputs["plan"],"arguments",["never-execute"]),(self.allocation,"command","never-execute"),(self.allocation["bindings"]["executables"],"shell",{})]:
            mapping[key]=value;self.save()
            with self.subTest(key=key),self.assertRaises(UpgradeRefused):self.value()
            del mapping[key];self.save()
        self.unchanged_installation()

    def test_same_bytes_replaced_private_record_refuses_retained_controller_input(self):
        value=self.value();path=self.directory/"inputs.json";other=self.directory/"replacement";other.write_bytes(path.read_bytes());other.chmod(0o600);os.replace(other,path)
        with self.assertRaises(UpgradeRefused):value.observe_inputs()
        self.unchanged_installation()

    def test_same_bytes_replaced_archive_refuses_old_and_new_input_read(self):
        value=self.value();other=self.base/"replacement-archive";other.write_bytes(self.archive.read_bytes());other.chmod(0o600);os.replace(other,self.archive)
        for action in [value.observe_inputs,self.value]:
            with self.assertRaises(UpgradeRefused):action()
        self.unchanged_installation()

    def test_changed_directory_identity_refuses_and_retains_original_resources(self):
        value=self.value();storage=self.root/"storage";original=storage.stat().st_ino;retained=self.base/"retained-storage";storage.rename(retained);storage.mkdir(mode=0o700)
        for action in [value.observe_inputs,self.value]:
            with self.assertRaises(UpgradeRefused):action()
        self.assertEqual(retained.stat().st_ino,original)
        self.assertFalse(list(retained.iterdir()))

    def test_alias_hardlink_shared_file_and_shared_directory_refuse_unchanged(self):
        path=self.directory/"allocation.json";raw=path.read_bytes();link=self.directory/"alias";os.link(path,link)
        with self.assertRaises(UpgradeRefused):self.value()
        link.unlink();path.chmod(0o644)
        with self.assertRaises(UpgradeRefused):self.value()
        path.chmod(0o600);self.directory.chmod(0o755)
        with self.assertRaises(UpgradeRefused):self.value()
        self.directory.chmod(0o700);path.rename(link);path.symlink_to(link)
        with self.assertRaises(UpgradeRefused):self.value()
        self.assertEqual(link.read_bytes(),raw)
        self.unchanged_installation()

    def test_wrong_bootstrap_digest_uuid_or_password_cannot_adopt_sealed_request(self):
        original=self.inputs["plan"]["bootstrap_request_sha256"];self.inputs["plan"]["bootstrap_request_sha256"]="0"*64;self.save()
        with self.assertRaises(UpgradeRefused):self.value()
        self.inputs["plan"]["bootstrap_request_sha256"]=original
        for key,changed in [("installation",str(uuid.uuid4())),("request","not-canonical"),("password","short")]:
            previous=self.inputs["bootstrap"][key];self.inputs["bootstrap"][key]=changed;self.inputs["plan"]["bootstrap_request_sha256"]=bootstrap_digest(self.inputs["bootstrap"]);self.save()
            with self.subTest(field=key),self.assertRaises((UpgradeRefused,EnrollmentRefused)):self.value()
            self.inputs["bootstrap"][key]=previous;self.inputs["plan"]["bootstrap_request_sha256"]=original;self.save()
        self.unchanged_installation()
