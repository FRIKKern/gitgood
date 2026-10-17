"""Fresh process status: portable grammar and isolated actual Root/child checks."""
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import native_service_scope as service


UID=65503
GID=1000
CAPABILITIES=('CapInh','CapPrm','CapEff','CapBnd','CapAmb')


def status_text():
    return ('Name:\tsynthetic\nUid:\t'+(' '.join([str(UID)]*4))+'\nGid:\t'+
        (' '.join([str(GID)]*4))+'\nGroups:\t1000\n'+
        ''.join(name+':\t0000000000000000\n' for name in CAPABILITIES)+'NoNewPrivs:\t1\n')


class ProcessStatusParsingTest(unittest.TestCase):
    def identity(self,status,*,uid=UID,gid=GID,state='S'):
        self.reads=[]
        def read(path,*_):
            name=Path(path).name;self.reads.append(name)
            if name=='stat':return ('123 (synthetic) '+' '.join([state]+['0']*18+['999'])).encode()
            if name=='status':return status.encode()
            if name=='cgroup':return b'0::/synthetic\n'
            self.fail('Unexpected process observation')
        with (patch.object(service,'read_bytes',side_effect=read),
                patch.object(service.Path,'stat',return_value=SimpleNamespace(st_uid=UID)),
                patch.object(service.os,'readlink',side_effect=['mnt:[1]','cgroup:[2]'])):
            return service.process_identity(123,uid,gid,'/synthetic')

    def test_complete_original_result_and_fresh_read_order(self):
        value=self.identity(status_text())
        self.assertEqual(value,{'pid':123,'birth':'999','uid':UID,
            'security':{'gid':GID,'supplementary_groups':[GID],
                'capabilities':{name:0 for name in CAPABILITIES},'no_new_privileges':True},
            'mount_namespace':'mnt:[1]','cgroup_namespace':'cgroup:[2]'})
        self.assertEqual(self.reads,['stat','status','cgroup'])

    def test_each_required_privilege_field_rejects_missing_or_duplicate_values(self):
        original=status_text()
        for name in ['Gid','Groups',*CAPABILITIES,'NoNewPrivs']:
            line=next(line for line in original.splitlines(True) if line.startswith(name+':'))
            for changed in [original.replace(line,''),original+line]:
                with self.subTest(field=name),self.assertRaises(service.ServiceRefused):
                    service.process_security(changed,GID)

    def test_identity_uid_and_gid_multiplicity_and_tokens_refuse_before_cgroup_reads(self):
        original=status_text()
        for name in ['Uid','Gid']:
            line=next(line for line in original.splitlines(True) if line.startswith(name+':'))
            for changed in [original.replace(line,''),original+line,
                    original.replace(line,name+':\t1 1 1\n'),
                    original.replace(line,name+':\t1 2 1 1\n'),
                    original.replace(line,' '+line)]:
                with self.subTest(field=name),self.assertRaises(service.ServiceRefused):self.identity(changed)
                self.assertEqual(self.reads,['stat','status'])

    def test_unknown_duplicate_fields_and_unrelated_uid_remain_ignored_by_security_api(self):
        original=status_text();expected=service.process_security(original,GID)
        value=original+'Unknown:\tfirst\nUnknown:\tsecond\nMalformed unrelated line\nUid:\tforeign\n'
        self.assertEqual(service.process_security(value,GID),expected)
        self.assertEqual(service.process_security(original.replace('\n','\r\n'),GID),expected)

    def test_group_token_and_privilege_predicates_are_unchanged(self):
        original=status_text()
        for groups,expected in [('',[]),('1000 1000',[1000]),('001000',[1000])]:
            self.assertEqual(service.process_security(original.replace('Groups:\t1000','Groups:\t'+groups),GID)['supplementary_groups'],expected)
        for groups in ['0','1000 27','-1000','+1000','x','1'*11,' '.join(['1000']*65)]:
            with self.subTest(groups=groups),self.assertRaises(service.ServiceRefused):
                service.process_security(original.replace('Groups:\t1000','Groups:\t'+groups),GID)
        for name in CAPABILITIES:
            with self.subTest(field=name),self.assertRaises(service.ServiceRefused):
                service.process_security(original.replace(name+':\t0000000000000000',name+':\t0000000000000001'),GID)
        with self.assertRaises(service.ServiceRefused):service.process_security(original.replace('NoNewPrivs:\t1','NoNewPrivs:\t0'),GID)

    def test_invalid_gid_still_refuses_before_reading_a_status_object(self):
        for gid in [True,False,0,-1,2**32,'1000']:
            with self.subTest(gid=gid),self.assertRaises(service.ServiceRefused):service.process_security(object(),gid)

    def test_each_public_security_observation_parses_only_its_fresh_text_once(self):
        class Counted(str):
            calls=0
            def splitlines(self,*args,**kwargs):
                self.calls+=1;return super().splitlines(*args,**kwargs)
        first=Counted(status_text());second=Counted(status_text().replace('NoNewPrivs:\t1','NoNewPrivs:\t0'))
        self.assertTrue(service.process_security(first,GID)['no_new_privileges'])
        with self.assertRaises(service.ServiceRefused):service.process_security(second,GID)
        self.assertEqual((first.calls,second.calls),(1,1))

    def test_process_identity_never_reuses_prior_status_and_preserves_zombie_refusal(self):
        self.identity(status_text())
        with self.assertRaises(service.ServiceRefused):self.identity(status_text().replace('NoNewPrivs:\t1','NoNewPrivs:\t0'))
        self.assertEqual(self.reads,['stat','status','cgroup'])
        for state in ['Z','X']:
            with self.subTest(state=state),self.assertRaises(service.ServiceRefused):self.identity(status_text(),state=state)
            self.assertEqual(self.reads,['stat'])


@unittest.skipUnless(sys.platform=='linux' and getattr(os,'getuid',lambda:1)()==0,
    'actual isolated Linux child credential and namespace observations')
class ActualProcessIdentityTest(unittest.TestCase):
    def child(self):
        command=['/usr/bin/setpriv','--reuid='+str(UID),'--regid='+str(GID),'--clear-groups',
            '--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all','--no-new-privs',
            sys.executable,'-I','-S','-B','-c',"import time;print('ready',flush=True);time.sleep(45)"]
        child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        def close():
            if child.poll() is None:child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
            child.stdout.close()
        self.addCleanup(close)
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout,selectors.EVENT_READ)
            self.assertTrue(selector.select(5),'Owned child did not become ready')
            self.assertEqual(child.stdout.readline(32),b'ready\n')
        group=Path('/proc',str(child.pid),'cgroup').read_text().splitlines()
        self.assertEqual(len(group),1);self.assertTrue(group[0].startswith('0::'))
        return child,group[0][3:]

    def test_twenty_actual_fresh_observations_retain_original_identity_and_zero_privileges(self):
        child,group=self.child();expected=service.process_identity(child.pid,UID,GID,group)
        self.assertEqual(expected['security'],{'gid':GID,'supplementary_groups':[],
            'capabilities':{name:0 for name in CAPABILITIES},'no_new_privileges':True})
        started=time.monotonic_ns()
        for _ in range(20):self.assertEqual(service.process_identity(child.pid,UID,GID,group),expected)
        print('actual_process_identity_observations=20 elapsed_ms='+str((time.monotonic_ns()-started)//1000000),flush=True)

    def test_wrong_uid_gid_or_cgroup_refuses_without_changing_owned_child(self):
        child,group=self.child();original=service.process_identity(child.pid,UID,GID,group)
        for uid,gid,selected in [(UID+1,GID,group),(UID,GID+1,group),(UID,GID,group+'-foreign')]:
            with self.subTest(uid=uid,gid=gid),self.assertRaises(service.ServiceRefused):
                service.process_identity(child.pid,uid,gid,selected)
        self.assertEqual(service.process_identity(child.pid,UID,GID,group),original)

    def test_original_child_loss_cannot_return_the_previously_observed_identity(self):
        child,group=self.child();service.process_identity(child.pid,UID,GID,group)
        child.terminate();child.wait(timeout=5)
        with self.assertRaises((service.ServiceRefused,OSError)):service.process_identity(child.pid,UID,GID,group)


if __name__=='__main__':unittest.main()
