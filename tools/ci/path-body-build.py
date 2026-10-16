#!/usr/bin/env python3
"""Future hosted-only diagnostic builder; no product or local dependency."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import sysconfig
import urllib.parse
import urllib.request
import zipfile

from path_body_source import select_source

WHEEL_URL = ('https://files.pythonhosted.org/packages/a9/5e/'
    'b590aff6c332fb6bf5c12d2fae0383f6e866b47d0b1efd8bdc9443198ce0/'
    'cython-3.1.8-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl')
WHEEL_BYTES = 3314265
WHEEL_SHA256 = 'd1bcbed7578f1986a61471476ea5deb0806591aa477230954dd9898a25d0f4e2'
DIRECTIVES = ('language_level=3,binding=True,annotation_typing=False,infer_types=False,'
    'boundscheck=True,wraparound=True,initializedcheck=True,nonecheck=True,cdivision=False,'
    'profile=False,linetrace=False')

# The donor bodies use this C helper for LOAD_GLOBAL equivalents. Keep live
# original dictionaries, including the original functions' builtins dictionary;
# never copy their values or substitute the original classes.
HEADER = '''# cython: language_level=3
cdef object _original_globals = None
cdef object _original_builtins = None
cdef object _missing = object()

def bind_original(original_globals, original_builtins):
    global _original_globals, _original_builtins
    if type(original_globals) is not dict or type(original_builtins) is not dict:
        return False
    if _original_globals is not None:
        return _original_globals is original_globals and _original_builtins is original_builtins
    _original_globals = original_globals
    _original_builtins = original_builtins
    return True

cdef inline object _gitgood_path_body_name(object name):
    cdef object value
    if _original_globals is None:
        raise RuntimeError('Unbound path body diagnostic')
    value = _original_globals.get(name, _missing)
    if value is _missing:
        value = _original_builtins.get(name, _missing)
    if value is _missing:
        raise NameError("name " + repr(name) + " is not defined", name=name)
    return value

'''


def require(value):
    if not value:raise ValueError('Hosted path body build invariant')


def read_stdlib_source():
    path=Path(sysconfig.get_path('stdlib'))/'pathlib.py'
    require(path.is_absolute() and path.resolve(strict=True)==path)
    for parent in path.parents:
        value=parent.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid==0 and not value.st_mode & 0o022)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as source:
        before=os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid==before.st_gid==0
            and before.st_nlink==1 and not before.st_mode & 0o022 and 0<before.st_size<=262144)
        raw=source.read(262145);after=os.fstat(source.fileno())
        fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_uid','st_gid','st_nlink')
        require(len(raw)==before.st_size and all(getattr(before,key)==getattr(after,key)
            ==getattr(path.lstat(),key) for key in fields))
    return raw.decode('utf-8')


def download_compiler(directory):
    path=directory/'compiler.whl';hashed=hashlib.sha256();size=0
    with urllib.request.urlopen(WHEEL_URL,timeout=30) as response,path.open('xb') as output:
        require(urllib.parse.urlparse(response.geturl()).hostname=='files.pythonhosted.org')
        while block:=response.read(65536):
            size+=len(block);require(size<=WHEEL_BYTES);hashed.update(block);output.write(block)
    require(size==WHEEL_BYTES and hashed.hexdigest()==WHEEL_SHA256)
    vendor=directory/'compiler';vendor.mkdir(mode=0o755)
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist();require(0<len(entries)<=5000)
        seen=set();total=0
        for entry in entries:
            name=entry.filename;relative=PurePosixPath(name)
            require(name not in seen and relative.parts and not relative.is_absolute()
                and relative.as_posix()==name.rstrip('/') and '..' not in relative.parts
                and not any(char in name for char in '\\:\0'))
            seen.add(name);mode=entry.external_attr>>16
            require(stat.S_IFMT(mode) in {0,stat.S_IFREG,stat.S_IFDIR} and not entry.flag_bits & 1)
            total+=entry.file_size;require(0<=entry.file_size<=16777216 and total<=67108864)
        archive.extractall(vendor)
    return vendor


def main():
    require(sys.platform=='linux' and sys.version_info[:2]==(3,12) and sys.implementation.name=='cpython'
        and platform.machine()=='x86_64' and os.getuid()!=0
        and os.environ.get('GITHUB_ACTIONS')=='true'
        and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted')
    directory=Path(__file__).resolve().parents[2]/'.gitgood/path-body-probe'
    for output in {Path('/'),directory.parent.resolve()}:
        require(shutil.disk_usage(output).free-268435456>=20*1024**3)
    raw=read_stdlib_source();body,manifest=select_source(raw)
    directory.mkdir(mode=0o755)  # Refuse an existing build or retained output.
    vendor=download_compiler(directory)
    original=directory/'pathlib-original.py';original.write_text(raw,encoding='utf-8')
    source=directory/'path-body-donor.pyx';generated=HEADER+body;source.write_text(generated,encoding='utf-8')
    c_source=directory/'path-body-donor.c'
    environment={**os.environ,'PYTHONPATH':str(vendor),'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
    subprocess.run([sys.executable,'-B','-s','-m','Cython','--module-name','_path_body_probe',
        '-X',DIRECTIVES,'-o',str(c_source),str(source)],env=environment,check=True,timeout=120)
    suffix=sysconfig.get_config_var('EXT_SUFFIX');include=Path(sysconfig.get_path('include'))
    require(type(suffix) is str and '/' not in suffix and suffix.endswith('.so') and (include/'Python.h').is_file())
    extension=directory/('_path_body_probe'+suffix)
    subprocess.run(['/usr/bin/cc','-shared','-fPIC','-O2','-std=c11','-fwrapv','-fno-strict-aliasing',
        '-Wall','-Wextra','-I'+str(include),str(c_source),'-o',str(extension)],check=True,timeout=120)
    require(0<extension.stat().st_size<=8388608)
    manifest.update(compiler_version='3.1.8',compiler_wheel_sha256=WHEEL_SHA256,
        compiler_wheel_bytes=WHEEL_BYTES,compiler_directives=DIRECTIVES,python_version=platform.python_version(),
        donor_source_sha256=hashlib.sha256(generated.encode()).hexdigest(),
        c_source_sha256=hashlib.sha256(c_source.read_bytes()).hexdigest(),
        elf_sha256=hashlib.sha256(extension.read_bytes()).hexdigest(),compiled=True,runtime_verified=False,
        production_adopted=False)
    (directory/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
