"""Fixed read-only systemd properties; one connection, no reconnect after refusal."""
import ctypes
import os
from pathlib import Path
import uuid

from native_service_scope import ServiceRefused, _CapturedRootFiles

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
            if signature=='s': result=self._string(message)
            elif signature in ['u','b']:
                value=ctypes.c_uint32() if signature=='u' else ctypes.c_int()
                require(self.library.sd_bus_message_read_basic(message,signature.encode(),ctypes.byref(value))==1)
                if signature=='b': require(value.value in [0,1])
                result=str(value.value) if signature=='u' else ('yes' if value.value else 'no')
            else:
                require(self.library.sd_bus_message_enter_container(message,b'a',b's')==1)
                values=[]
                while self.library.sd_bus_message_at_end(message,0)==0:
                    require(len(values)<32);values.append(self._string(message))
                require(self.library.sd_bus_message_exit_container(message)>=0)
                result=' '.join(values)
            require(self.library.sd_bus_message_at_end(message,0)==1)
            return result
        except BaseException:
            self.close();raise
        finally:
            if message: self.library.sd_bus_message_unref(message)

    def manager_version(self):
        return self._get('/org/freedesktop/systemd1','org.freedesktop.systemd1.Manager','Version','s')

    def _get_many(self,path,properties):
        """Read selected live properties; publish nothing until the batch closes."""
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

    def unit_properties(self,unit,*,_interface_snapshots=False):
        try:
            require(type(_interface_snapshots) is bool)
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
        if not _interface_snapshots:return self._get_many(path,properties)
        try:
            # Root's repeated stage guards read the same closed field set in
            # two fresh interface replies. Ordinary selected reads are intact.
            require(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0)
            result={}
            for interface in ('org.freedesktop.systemd1.Unit','org.freedesktop.systemd1.Service'):
                signatures={name:signature for kind,name,signature in properties if kind==interface}
                result.update(self._get_all(path,interface,signatures))
            require(set(result)=={name for _,name,_ in properties})
            return result
        except BaseException:
            self.close();raise
