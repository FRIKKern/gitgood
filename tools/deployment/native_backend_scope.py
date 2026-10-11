"""Fixed protected server scope custody; no allocator enrollment or authority."""
import json
from pathlib import Path

from native_durable_database import unique
from native_kernel_backend import _validate_scope
from native_service_scope import root_file, _CapturedRootFiles
from resource_generations import canonical, identifier


class NativeBackendScope:
    def __init__(self, installation, boot_id):
        identifier(installation); identifier(boot_id)
        self.path = Path('/etc/gitgood/installations')/installation/('backend-kernel-'+boot_id+'.json')
        self.fingerprint=_CapturedRootFiles._fingerprint(self.path,4096,False)
        self.identity,self.raw = root_file(self.path,4096)
        if _CapturedRootFiles._fingerprint(self.path,4096,False)!=self.fingerprint:
            raise ValueError('Protected native backend scope changed')
        seal=json.loads(self.raw,object_pairs_hook=unique)
        if (type(seal) is not dict or set(seal)!={'protocol','kind','installation','server_scope'} or
                type(seal['protocol']) is not int or seal['protocol']!=2 or
                seal['kind']!='native_backend_kernel_scope_seal' or seal['installation']!=installation or
                self.raw!=canonical(seal)):
            raise ValueError('Protected native backend scope unavailable')
        _validate_scope(seal['server_scope'])
        if seal['server_scope']['boot_id']!=boot_id:
            raise ValueError('Protected native backend scope unavailable')
        self.scope=json.loads(canonical(seal['server_scope']))
        self.usable=True

    def check(self):
        try:
            if (not self.usable or _CapturedRootFiles._fingerprint(self.path,4096,False)!=self.fingerprint or
                    root_file(self.path,4096)!=(self.identity,self.raw) or
                    _CapturedRootFiles._fingerprint(self.path,4096,False)!=self.fingerprint):
                raise ValueError('Protected native backend scope lost')
            return json.loads(canonical(self.scope))
        except Exception:
            self.usable=False
            raise ValueError('Protected native backend scope lost') from None
