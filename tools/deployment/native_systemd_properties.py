"""Fixed read-only systemd properties; one connection, no reconnect after refusal."""
import ctypes
import os
from pathlib import Path
import threading
import time
import uuid

from native_service_scope import ServiceRefused, _CapturedRootFiles

_MESSAGE_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p)

class BusRefused(ServiceRefused):
    pass

def require(value):
    if not value: raise BusRefused('Read-only system bus observation unavailable')

class ReadOnlySystemdProperties:
    def __init__(self):
        self.path=Path('/usr/lib/x86_64-linux-gnu/libsystemd.so.0').resolve(strict=True)
        self.files=_CapturedRootFiles()
        self.original=self.files.read(self.path)[0]
        self.library=ctypes.CDLL(str(self.path))
        require(self.files.read(self.path)[0]==self.original)
        self.files.frozen=True
        pointer=ctypes.c_void_p;string=ctypes.c_char_p
        signatures={
            'sd_bus_new':([ctypes.POINTER(pointer)],ctypes.c_int),
            'sd_bus_set_address':([pointer,string],ctypes.c_int),
            'sd_bus_set_bus_client':([pointer,ctypes.c_int],ctypes.c_int),
            'sd_bus_set_method_call_timeout':([pointer,ctypes.c_uint64],ctypes.c_int),
            'sd_bus_start':([pointer],ctypes.c_int),
            'sd_bus_get_property':([pointer,string,string,string,string,pointer,ctypes.POINTER(pointer),string],ctypes.c_int),
            'sd_bus_call_method':([pointer,string,string,string,string,pointer,ctypes.POINTER(pointer),string],ctypes.c_int),
            'sd_bus_message_new_method_call':([pointer,ctypes.POINTER(pointer),string,string,string,string],ctypes.c_int),
            'sd_bus_message_append_basic':([pointer,ctypes.c_char,pointer],ctypes.c_int),
            'sd_bus_call_async':([pointer,ctypes.POINTER(pointer),pointer,_MESSAGE_HANDLER,pointer,ctypes.c_uint64],ctypes.c_int),
            'sd_bus_process':([pointer,ctypes.POINTER(pointer)],ctypes.c_int),
            'sd_bus_wait':([pointer,ctypes.c_uint64],ctypes.c_int),
            'sd_bus_get_current_slot':([pointer],pointer),
            'sd_bus_slot_unref':([pointer],pointer),
            'sd_bus_message_is_method_error':([pointer,string],ctypes.c_int),
            'sd_bus_message_has_signature':([pointer,string],ctypes.c_int),
            'sd_bus_message_read_basic':([pointer,ctypes.c_char,pointer],ctypes.c_int),
            'sd_bus_message_enter_container':([pointer,ctypes.c_char,string],ctypes.c_int),
            'sd_bus_message_exit_container':([pointer],ctypes.c_int),
            'sd_bus_message_at_end':([pointer,ctypes.c_int],ctypes.c_int),
            'sd_bus_message_skip':([pointer,string],ctypes.c_int),
            'sd_bus_message_unref':([pointer],pointer),
            'sd_bus_flush_close_unref':([pointer],pointer)}
        for name,(arguments,result) in signatures.items():
            function=getattr(self.library,name);function.argtypes=arguments;function.restype=result
        self.bus=pointer();self.usable=False
        try:
            require(self.library.sd_bus_new(ctypes.byref(self.bus))>=0)
            require(self.library.sd_bus_set_address(self.bus,b'unix:path=/run/dbus/system_bus_socket')>=0)
            require(self.library.sd_bus_set_bus_client(self.bus,1)>=0)
            require(self.library.sd_bus_set_method_call_timeout(self.bus,5_000_000)>=0)
            require(self.library.sd_bus_start(self.bus)>=0)
            self.usable=True
        except BaseException:
            self.close();raise

    def close(self):
        self.usable=False
        self.files.usable=False
        if self.bus:
            self.library.sd_bus_flush_close_unref(self.bus);self.bus=ctypes.c_void_p()

    def _string(self,message):
        value=ctypes.c_char_p()
        require(self.library.sd_bus_message_read_basic(message,b's',ctypes.byref(value))==1)
        require(value.value is not None and len(value.value)<=2048)
        return value.value.decode('ascii',errors='strict')

    def _get(self,path,interface,name,signature):
        try:
            require(self.usable)
            require(self.files.read(self.path)[0]==self.original)
            result=self._read_property(path,interface,name,signature)
            require(self.files.read(self.path)[0]==self.original)
            return result
        except BaseException:
            self.close();raise

    def _read_property(self,path,interface,name,signature):
        """Decode one live reply inside an already bracketed library observation."""
        message=ctypes.c_void_p()
        try:
            require(self.usable and signature in ['s','u','b','as'])
            require(self.library.sd_bus_get_property(self.bus,b'org.freedesktop.systemd1',path.encode(),interface.encode(),name.encode(),None,ctypes.byref(message),signature.encode())==0)
            return self._read_value(message,signature)
        except BaseException:
            self.close();raise
        finally:
            if message: self.library.sd_bus_message_unref(message)

    def _read_value(self,message,signature):
        if signature=='s': result=self._string(message)
        elif signature in ['u','b']:
            value=ctypes.c_uint32() if signature=='u' else ctypes.c_int()
            require(self.library.sd_bus_message_read_basic(message,signature.encode(),ctypes.byref(value))==1)
            if signature=='b': require(value.value in [0,1])
            result=str(value.value) if signature=='u' else ('yes' if value.value else 'no')
        else:
            require(signature=='as')
            require(self.library.sd_bus_message_enter_container(message,b'a',b's')==1)
            values=[]
            while self.library.sd_bus_message_at_end(message,0)==0:
                require(len(values)<32);values.append(self._string(message))
            require(self.library.sd_bus_message_exit_container(message)>=0)
            result=' '.join(values)
        require(self.library.sd_bus_message_at_end(message,0)==1)
        return result

    def manager_version(self):
        return self._get('/org/freedesktop/systemd1','org.freedesktop.systemd1.Manager','Version','s')

    def _get_many(self,path,properties):
        """Queue only selected Get calls; publish no partial or retained result."""
        try:
            require(self.usable and type(path) is str and path.startswith('/') and len(path)<=1024 and '\0' not in path)
            require(type(properties) is list and 0<len(properties)<=32)
            require(all(type(item) is tuple and len(item)==3 for item in properties))
            require(all(type(interface) is str and type(name) is str and signature in ['s','u','b','as']
                and 0<len(interface)<=256 and 0<len(name)<=256 and '\0' not in interface+name
                for interface,name,signature in properties))
            require(len({name for _,name,_ in properties})==len(properties))
            properties=tuple(properties)
            require(self.files.read(self.path)[0]==self.original)
            result=self._read_selected(path,properties)
            require(self.files.read(self.path)[0]==self.original)
            return result
        except BaseException:
            self.close();raise

    def _read_selected(self,path,properties):
        require(not getattr(self,'_selected_active',False))
        self._selected_active=True
        owner=(os.getpid(),threading.get_ident());slots=[];result={};failed=False
        deadline=time.monotonic()+5
        @_MESSAGE_HANDLER
        def completed(message,userdata,_error):
            nonlocal failed
            try:
                require(not failed and self.usable and owner==(os.getpid(),threading.get_ident()))
                require(type(userdata) is int and 1<=userdata<=len(slots))
                index=userdata-1;_,name,signature=properties[index]
                require(name not in result and slots[index].value
                    and self.library.sd_bus_get_current_slot(self.bus)==slots[index].value)
                require(self.library.sd_bus_message_is_method_error(message,None)==0)
                require(self.library.sd_bus_message_has_signature(message,b'v')==1)
                require(self.library.sd_bus_message_enter_container(message,b'v',signature.encode())==1)
                value=self._read_value(message,signature)
                require(self.library.sd_bus_message_exit_container(message)>=0)
                require(self.library.sd_bus_message_at_end(message,0)==1)
                result[name]=value
            except BaseException:
                # Never allow a Python exception to escape a native callback.
                failed=True
            return 1
        try:
            for index,(interface,name,_) in enumerate(properties):
                require(time.monotonic()<deadline)
                message=ctypes.c_void_p();slot=ctypes.c_void_p();slots.append(slot)
                try:
                    require(self.library.sd_bus_message_new_method_call(self.bus,ctypes.byref(message),
                        b'org.freedesktop.systemd1',path.encode(),b'org.freedesktop.DBus.Properties',b'Get')>=0)
                    for value in (interface,name):
                        require(self.library.sd_bus_message_append_basic(message,b's',ctypes.c_char_p(value.encode()))>=0)
                    require(self.library.sd_bus_call_async(self.bus,ctypes.byref(slot),message,completed,
                        ctypes.c_void_p(index+1),5_000_000)>=0 and slot.value)
                finally:
                    if message:self.library.sd_bus_message_unref(message)
            processed=0
            while len(result)<len(properties):
                require(not failed and owner==(os.getpid(),threading.get_ident()) and time.monotonic()<deadline)
                processed+=1;require(processed<=4096)
                status=self.library.sd_bus_process(self.bus,None);require(status>=0)
                if status==0:
                    remaining=deadline-time.monotonic();require(remaining>0)
                    require(self.library.sd_bus_wait(self.bus,max(1,int(remaining*1000000)))>=0)
            require(not failed and set(result)=={name for _,name,_ in properties})
            return result
        finally:
            # Slots own their pending calls. Keep the callback alive until all
            # slots are cancelled; callback reply messages are borrowed only.
            for slot in reversed(slots):
                if slot:self.library.sd_bus_slot_unref(slot)
            self._selected_active=False

    def _get_many_serial(self,path,properties):
        """Retained serial reference for actual typed-reply comparison tests."""
        try:
            require(self.usable and type(properties) is list and 0<len(properties)<=32)
            require(all(type(item) is tuple and len(item)==3 for item in properties))
            require(all(type(interface) is str and type(name) is str and signature in ['s','u','b','as']
                        for interface,name,signature in properties))
            require(len({name for _,name,_ in properties})==len(properties))
            require(self.files.read(self.path)[0]==self.original)
            result={name:self._read_property(path,interface,name,signature) for interface,name,signature in properties}
            require(self.files.read(self.path)[0]==self.original)
            return result
        except BaseException:
            self.close();raise

    def _get_all(self,path,interface,signatures):
        """Read one live interface reply; never cache manager or unit values."""
        message=ctypes.c_void_p()
        try:
            require(self.usable and type(signatures) is dict and 0<len(signatures)<=32)
            require(all(type(name) is str and signature in ['s','u','b','as'] for name,signature in signatures.items()))
            require(self.files.read(self.path)[0]==self.original)
            require(self.library.sd_bus_call_method(self.bus,b'org.freedesktop.systemd1',path.encode(),
                b'org.freedesktop.DBus.Properties',b'GetAll',None,ctypes.byref(message),b's',interface.encode())>=0)
            require(self.library.sd_bus_message_enter_container(message,b'a',b'{sv}')==1)
            seen=set();result={}
            while self.library.sd_bus_message_at_end(message,0)==0:
                require(len(seen)<512)
                require(self.library.sd_bus_message_enter_container(message,b'e',b'sv')==1)
                name=self._string(message);require(name and name not in seen);seen.add(name)
                if name in signatures:
                    signature=signatures[name]
                    require(self.library.sd_bus_message_enter_container(message,b'v',signature.encode())==1)
                    if signature=='s':value=self._string(message)
                    elif signature in ['u','b']:
                        field=ctypes.c_uint32() if signature=='u' else ctypes.c_int()
                        require(self.library.sd_bus_message_read_basic(message,signature.encode(),ctypes.byref(field))==1)
                        if signature=='b':require(field.value in [0,1])
                        value=str(field.value) if signature=='u' else ('yes' if field.value else 'no')
                    else:
                        require(self.library.sd_bus_message_enter_container(message,b'a',b's')==1)
                        values=[]
                        while self.library.sd_bus_message_at_end(message,0)==0:
                            require(len(values)<32);values.append(self._string(message))
                        require(self.library.sd_bus_message_exit_container(message)>=0)
                        value=' '.join(values)
                    require(self.library.sd_bus_message_at_end(message,0)==1)
                    require(self.library.sd_bus_message_exit_container(message)>=0)
                    result[name]=value
                else:
                    require(self.library.sd_bus_message_skip(message,b'v')>=0)
                require(self.library.sd_bus_message_at_end(message,0)==1)
                require(self.library.sd_bus_message_exit_container(message)>=0)
            require(self.library.sd_bus_message_exit_container(message)>=0)
            require(self.library.sd_bus_message_at_end(message,0)==1 and set(result)==set(signatures))
            require(self.files.read(self.path)[0]==self.original)
            return result
        except BaseException:
            self.close();raise
        finally:
            if message:self.library.sd_bus_message_unref(message)

    def unit_properties(self,unit):
        try:
            require(type(unit) is str and unit.startswith('gitgood-installation-') and unit.endswith('.service'))
            installation=unit[len('gitgood-installation-'):-len('.service')]
            require(str(uuid.UUID(installation))==installation)
        except BaseException:
            self.close();raise
        suffix=''.join(character if character.isascii() and character.isalnum() else '_'+format(ord(character),'02x') for character in unit)
        path='/org/freedesktop/systemd1/unit/'+suffix
        unit_names=['Id','LoadState','ActiveState','SubState','FragmentPath','DropInPaths']
        service_names=['User','Group','MainPID','ControlGroup','Delegate','DelegateSubgroup','DelegateControllers','KillMode','Restart']
        properties=[]
        for interface,names in [('Unit',unit_names),('Service',service_names)]:
            properties += [('org.freedesktop.systemd1.'+interface,name,
                            {'MainPID':'u','Delegate':'b','DropInPaths':'as','DelegateControllers':'as'}.get(name,'s')) for name in names]
        return self._get_many(path,properties)
