"""Code context for complete native observation roles; source preparation only.

This context leaves SDK descriptors original. The fused C preparation and role
dispatch are not wired yet; this module establishes admission/teardown without
reusing a Root admission or a filesystem observation result.
"""
from contextlib import contextmanager
import os
import pathlib
import sys
import threading

import native_path_probe as sdk
from native_metadata_probe import require


class RoleContext:
    def __init__(self,loaded,*,owner_check=None):
        self.loaded=loaded;self.native=loaded.native
        self.owner_check=sdk.metadata.root_owner if owner_check is None else owner_check
        self.owner_check();sdk.sdk_environment();loaded.validate()
        prepared=sdk.Adapter(self.native,owner_check=owner_check,sdk_codes=loaded.codes,_prepare_only=True)
        self.owner=prepared.owner;self.originals=prepared.originals
        self.tables=prepared.binding_tables(sdk.DESCRIPTOR_APIS,originals=True)
        self.apis={name:getattr(self.native,name) for name in sdk.DESCRIPTOR_APIS}
        self.active=False;self.closed=False;self.broken=False;self.final_details=None
        self.plan=self.apis['descriptor_plan'](prepared.concrete,self.originals,*self.owner,256,prepared.import_globals)
        try:
            # The current context API requires issuing its descriptors once.
            # They are discarded here: no SDK class receives a replacement.
            self.apis['descriptor_entries'](self.plan)
            self.apis['descriptor_bind'](self.plan,self.tables,
                (pathlib,sdk.builtins,os,sys,sdk.posixpath,sdk.ntpath,self.native))
            require(self.sdk_original())
        except BaseException:
            pending=sys.exception()
            try:self.apis['descriptor_close'](self.plan)
            except BaseException:pass
            self.plan=None;self.tables=();self.closed=True;self.broken=True
            raise pending

    def sdk_original(self):
        return all(vars(owner).get(name) is original
            for (owner,name),original in zip(sdk.TARGETS,self.originals))

    def check(self):
        self.owner_check()
        require(not self.closed and not self.broken and self.owner==(os.getpid(),threading.get_ident()))

    @contextmanager
    def admitted(self):
        self.check();require(not self.active and self.sdk_original())
        self.loaded.validate()
        try:
            self.apis['descriptor_phase'](self.plan,0);self.active=True
            yield self
            self.check();require(self.sdk_original())
        finally:
            pending=sys.exception();failure=None
            try:self.apis['descriptor_phase'](self.plan,1)
            except BaseException as error:failure=error
            self.active=False;self.broken=failure is not None or not self.sdk_original()
            if pending is None:
                if failure is not None:raise failure
                require(not self.broken)

    def close(self):
        if self.closed:return
        require(not self.active);pending=sys.exception()
        try:
            self.apis['descriptor_close'](self.plan)
            self.final_details=self.apis['descriptor_counts'](self.plan)
            require(self.final_details['phase']=='closed' and not self.final_details['watching']
                and self.final_details['code_inputs']==0 and self.final_details['cache_entries']==0)
        except BaseException:
            self.broken=True
            if pending is None:raise
        finally:
            self.plan=None;self.tables=();self.closed=True
