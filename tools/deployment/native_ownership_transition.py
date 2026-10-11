"""Retained ownership transition bytes; this store grants no admission authority.

Only a live controller may supply the checks around its effects. Interrupted
writes are recoverable by that same retained object only when their exact bytes
and original inodes still agree. Unknown files are never removed or replaced.
"""
import hashlib
import itertools
import json
import os
import stat

from native_durable_database import unique
from native_ownership_markers import NativeOwnershipMarkers, fcntl
from native_ownership_records import require, record_name, validate_record
from resource_generations import canonical, identifier
from stage_native_artifact import publish_directory


FIELDS = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink')


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class OwnershipTransitionStore(NativeOwnershipMarkers):
    """Descriptor-based immutable receipts and no-replace marker handoff."""
    def __init__(self, storage, installation, identity):
        self.descriptors = {};self.identities = {};self.known = {};self.pending = {}
        self.moves = {};self.move_destinations = {};self.published = None;self.closed = False
        try:
            super().__init__(storage,installation,identity)
            require(fcntl is not None)
            fd = os.open(self.storage,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            self.descriptors['storage'] = fd
            require(self._identity(os.fstat(fd))==self.identity==self._identity(self.storage.lstat()))
            for role,name in [('records','.gitgood-ownership-v2'),('receipts','.gitgood-successors-v4')]:
                try:os.mkdir(name,0o700,dir_fd=fd);os.fsync(fd)
                except FileExistsError:pass
                child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                self.descriptors[role]=child;self.identities[role]=self._identity(os.fstat(child))
                self.known[role]={}
                for entry in self._names(role):
                    require(not entry.startswith('.partial-'))
                    if role=='records':identifier(entry.removesuffix('.json'));require(entry.endswith('.json'))
                    else:
                        claim,kind,suffix=entry.split('.')
                        identifier(claim);require(suffix=='json' and kind in {'reservation','assignment','intent','complete','old-marker'})
                    self.known[role][entry]=self.read(role,entry)
            self.check()
        except Exception:
            self.close();raise

    def _names(self, role):
        with os.scandir(self.descriptors[role]) as iterator:
            values=[item.name for item in itertools.islice(iterator,769)]
        require(len(values)<=768)
        return set(values)

    def _directories(self):
        require(not self.closed and self.storage.resolve(strict=True)==self.storage)
        fd=self.descriptors['storage']
        require(self._identity(os.fstat(fd))==self.identity==self._identity(self.storage.lstat()))
        for role,name in [('records','.gitgood-ownership-v2'),('receipts','.gitgood-successors-v4')]:
            require(self._identity(os.fstat(self.descriptors[role]))==self.identities[role])
            require(self._identity(os.stat(name,dir_fd=fd,follow_symlinks=False))==self.identities[role])

    def read(self, role, name):
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=self.descriptors[role])
        with os.fdopen(fd,'rb') as source:
            before=os.fstat(source.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1)
            require(stat.S_IMODE(before.st_mode)==0o600 and 0<before.st_size<=65536)
            raw=source.read(65537);after=os.fstat(source.fileno())
        named=os.stat(name,dir_fd=self.descriptors[role],follow_symlinks=False)
        fingerprint=tuple(getattr(after,key) for key in FIELDS)
        require(len(raw)==before.st_size and fingerprint==tuple(getattr(before,key) for key in FIELDS)
                ==tuple(getattr(named,key) for key in FIELDS))
        value=json.loads(raw,object_pairs_hook=unique);require(raw==canonical(value))
        return value,fingerprint

    def check(self):
        self._directories()
        # A no-replace rename may have completed before its acknowledgement or
        # directory fsync failed. Admit only this object's predeclared move.
        for name,capture in self.moves.items():
            if name.endswith('.old-marker.json') and name not in self.known['receipts'] and name in self._names('receipts'):
                actual=self.read('receipts',name)
                require(actual[0]==capture[0] and self._moved_identity(capture[1],actual[1]))
                self.known['receipts'][name]=actual
            elif name.endswith('.new-marker.json') and name not in self._names('receipts'):
                destination=self.move_destinations[name];actual=self.read('storage',destination)
                require(actual[0]==capture[0] and self._moved_identity(capture[1],actual[1]))
                self.known['receipts'].pop(name,None)
                if self.published is None:self.published=(destination,actual)
        if self.published is not None:
            require(self.read('storage',self.published[0])==self.published[1])
        for role,known in self.known.items():
            expected=set(known)
            for (pending_role,name),pending in self.pending.items():
                if pending_role!=role:continue
                partial='.partial-'+name
                names=self._names(role)
                require((name in names) != (partial in names))
                present=name if name in names else partial
                value,fingerprint=self.read(role,present)
                require(value==pending['value'])
                require((fingerprint[0],fingerprint[1],fingerprint[5],fingerprint[6],fingerprint[7])==pending['identity'])
                require(pending['fingerprint'] is not None)
                if present==partial:require(fingerprint==pending['fingerprint'])
                else:require(self._moved_identity(pending['fingerprint'],fingerprint))
                expected.add(present)
            for name,capture in known.items():require(self.read(role,name)==capture)
            require(self._names(role)==expected)
        self._directories()

    def put(self, role, name, value):
        """Retain one exact value; an interrupted complete partial keeps its inode."""
        self._directories();raw=canonical(value);require(0<len(raw)<=65536)
        require(role in self.known and '/' not in name and name.endswith('.json'))
        key=(role,name);partial='.partial-'+name;fd=self.descriptors[role]
        if name in self.known[role]:
            self.check();require(self.known[role][name][0]==value);return
        if key not in self.pending:
            self.check();require(len(self._names(role))<(128 if role=='records' else 768))
            require(name not in self._names(role) and partial not in self._names(role))
            descriptor=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=fd)
            created=os.fstat(descriptor)
            self.pending[key]={'value':json.loads(raw),'identity':(created.st_dev,created.st_ino,created.st_uid,created.st_mode,created.st_nlink),
                               'fingerprint':None}
            with os.fdopen(descriptor,'wb') as output:
                output.write(raw);output.flush()
                self.pending[key]['fingerprint']=tuple(getattr(os.fstat(output.fileno()),name) for name in FIELDS)
                os.fsync(output.fileno())
            os.fsync(fd)
        else:require(self.pending[key]['value']==value)
        self.check()
        if partial in self._names(role):
            opened=os.open(partial,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            try:os.fsync(opened)
            finally:os.close(opened)
            fixed='/proc/self/fd/'+str(fd)+'/'
            publish_directory(fixed+partial,fixed+name)
        os.fsync(fd)
        capture=self.read(role,name);require(capture[0]==value)
        self.known[role][name]=capture;del self.pending[key];self.check()

    def records(self):
        self.check();values={}
        for name,(value,_) in self.known['records'].items():
            validate_record(value,allow_legacy=True);require(record_name(value)==name)
            require(value['installation']==self.installation and value['scope']['uid']==self.identity['uid'])
            values[sha(value)]=json.loads(canonical(value))
        require(len(values)<=128)
        return values

    def marker(self, record):
        name='.gitgood-runtime-v2.json' if record['mode']=='runtime' else '.gitgood-maintenance-v2.json'
        return name,self._marker(record)

    def current_marker(self, record):
        name,value=self.marker(record)
        result=self.read('storage',name);require(result[0]==value)
        other='.gitgood-maintenance-v2.json' if record['mode']=='runtime' else '.gitgood-runtime-v2.json'
        self._absent_marker(self.descriptors['storage'],other)
        return name,result

    def no_marker(self):
        for name in ['.gitgood-runtime-v2.json','.gitgood-maintenance-v2.json']:
            self._absent_marker(self.descriptors['storage'],name)

    @staticmethod
    def _moved_identity(before,after):
        # rename changes ctime; all other original inode/content metadata stays.
        return before[:4]+before[5:]==after[:4]+after[5:]

    def publish(self, record, previous, captured_marker, check):
        fcntl.flock(self.descriptors['records'],fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:return self._publish(record,previous,captured_marker,check)
        finally:fcntl.flock(self.descriptors['records'],fcntl.LOCK_UN)

    def _publish(self, record, previous, captured_marker, check):
        """Journal all bytes before effects; never overwrite or unlink a marker.

        check is the controller's live admission, not a serializable receipt.
        The original marker inode moves to an immutable archive. A short gap is
        an explicitly journaled stopped state; partial publication grants no life.
        """
        validate_record(record);require(record['protocol']==4)
        claim=record['claim'];identifier(claim)
        old_name,old_capture=captured_marker if previous is not None else (None,None)
        new_name,new_marker=self.marker(record)
        intent={'protocol':4,'kind':'native_ownership_marker_transition','installation':self.installation,
                'claim':claim,'reservation_sha256':record['reservation_sha256'],
                'predecessor_sha256':sha(previous) if previous else None,'record_sha256':sha(record),
                'old_name':old_name,'old_marker':old_capture[0] if old_capture else None,
                'old_identity':list(old_capture[1]) if old_capture else None,
                'new_name':new_name,'new_marker':new_marker}
        check();self.put('receipts',claim+'.intent.json',intent);check()
        self.put('records',record_name(record),record);check()
        # The same live object records each expected move before attempting it,
        # so an fsync/acknowledgement interruption can reobserve exact outcomes.
        archive=claim+'.old-marker.json';temporary=claim+'.new-marker.json'
        if previous is not None:
            self._directories();check()
            if archive not in self.known['receipts']:
                if archive not in self._names('receipts'):
                    require(self.read('storage',old_name)==old_capture)
                    self.moves[archive]=old_capture
                    publish_directory('/proc/self/fd/'+str(self.descriptors['storage'])+'/'+old_name,
                                      '/proc/self/fd/'+str(self.descriptors['receipts'])+'/'+archive)
                else:require(self.moves.get(archive)==old_capture)
                moved=self.read('receipts',archive)
                require(moved[0]==old_capture[0] and self._moved_identity(old_capture[1],moved[1]))
                self.known['receipts'][archive]=moved
                os.fsync(self.descriptors['storage']);os.fsync(self.descriptors['receipts'])
            require(self.known['receipts'][archive][0]==old_capture[0])
            os.fsync(self.descriptors['storage']);os.fsync(self.descriptors['receipts'])
        check();self._directories()
        if temporary not in self.moves:
            self.no_marker();self.put('receipts',temporary,new_marker)
            self.moves[temporary]=self.known['receipts'][temporary]
            self.move_destinations[temporary]=new_name
        original=self.moves[temporary]
        if temporary in self._names('receipts'):
            require(self.read('receipts',temporary)==original);self.no_marker();check()
            publish_directory('/proc/self/fd/'+str(self.descriptors['receipts'])+'/'+temporary,
                              '/proc/self/fd/'+str(self.descriptors['storage'])+'/'+new_name)
        current=self.current_marker(record)
        require(current[1][0]==new_marker and self._moved_identity(original[1],current[1][1]))
        self.known['receipts'].pop(temporary,None)
        if self.published is None:self.published=current
        require(self.published==current)
        os.fsync(self.descriptors['storage']);os.fsync(self.descriptors['receipts'])
        check();self.check()
        complete={'protocol':4,'kind':'native_ownership_publication_receipt','installation':self.installation,
                  'claim':claim,'operation':record['operation'],'record_sha256':sha(record),
                  'intent_sha256':sha(intent),'marker_sha256':sha(new_marker)}
        self.put('receipts',claim+'.complete.json',complete);check()
        require(self.current_marker(record)==current)
        return {'protocol':4,'status':'retained','claim':claim,'operation':record['operation'],
                'record_sha256':sha(record),'marker_sha256':sha(new_marker),
                'ownership_marker_retained':True,'installation_readiness_established':False,
                'replacement_admitted':False,'writer_exclusion_established':False,
                'lifecycle_responsibility_admitted':False}

    def close(self):
        self.closed=True
        for fd in self.descriptors.values():os.close(fd)
        self.descriptors={}
