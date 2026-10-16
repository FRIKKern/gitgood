"""Pinned Root-interpreter experiment, only on a disposable hosted runner."""
import hashlib
import itertools
import json
import os
from pathlib import Path, PurePosixPath
import platform
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request

NAME = 'pypy3.11-v8.0.1-linux64'
ARCHIVE_SHA256 = '706965bcf372752ba69dafd59d860e51bc2fadbb0f8a47cec3426125d7058ceb'
URL = 'https://downloads.python.org/pypy/' + NAME + '.tar.gz'
ROOT = Path('/var/lib/gitgood-root-runtime-probe')
RUNTIME = ROOT / NAME
EXECUTABLE = RUNTIME / 'bin/pypy3.11'
MAX_ENTRIES = 30000
MAX_BYTES = 512 * 1024**2
MAX_ARCHIVE = 64 * 1024**2


def require(value):
    if not value:raise ValueError('Hosted Root runtime diagnostic invariant')


def host():
    require(sys.platform == 'linux' and platform.machine() == 'x86_64')
    require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
    require(os.environ.get('GITHUB_ACTIONS') == 'true'
        and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted')
    release = Path('/etc/os-release').read_text()
    require('ID=ubuntu\n' in release and 'VERSION_ID="24.04"\n' in release)


def root_directory(path):
    require(path.is_absolute() and path.resolve(strict=True) == path)
    for parent in (path, *path.parents):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0 and not info.st_mode & 0o022)


def members(source):
    result = [];names = set();planned = set();total = 0
    for member in itertools.islice(source, MAX_ENTRIES + 1):
        require(len(result) < MAX_ENTRIES and type(member.name) is str)
        name = member.name.rstrip('/');path = PurePosixPath(name)
        require(0 < len(name) <= 1024 and '\0' not in name and '\\' not in name)
        require(not path.is_absolute() and '..' not in path.parts and path.parts[0] == NAME)
        require(str(path) == name and name not in names);names.add(name)
        planned.update(str(item) for item in (path, *path.parents) if str(item) != '.')
        require(len(planned) <= MAX_ENTRIES)
        require(member.isdir() or member.isreg() or member.issym() or member.islnk())
        require(type(member.size) is int and 0 <= member.size <= 128 * 1024**2)
        if member.isreg():total += member.size
        require(total <= MAX_BYTES)
        if member.issym() or member.islnk():
            require(type(member.linkname) is str and 0 < len(member.linkname) <= 1024 and '\0' not in member.linkname)
            target = PurePosixPath(member.linkname)
            require(not target.is_absolute())
            joined = str(path.parent / target) if member.issym() else str(target)
            normalized = PurePosixPath(posixpath.normpath(joined))
            require(normalized.parts and normalized.parts[0] == NAME and '..' not in normalized.parts)
        result.append(member)
    require(result and total > 0)
    return result


def file_hash(path):
    with path.open('rb') as source:return hashlib.file_digest(source, 'sha256').hexdigest()


def tree_identity(root):
    root_directory(root)
    paths = list(itertools.islice(root.rglob('*'), MAX_ENTRIES + 1))
    require(0 < len(paths) <= MAX_ENTRIES)
    digest = hashlib.sha256();total = 0
    for path in sorted(paths):
        info = path.lstat()
        require(info.st_uid == info.st_gid == 0)
        require(stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022)
        require(path.resolve(strict=True).is_relative_to(root))
        relative = path.relative_to(root).as_posix()
        if stat.S_ISLNK(info.st_mode):value = 'link:' + os.readlink(path)
        elif stat.S_ISDIR(info.st_mode):value = 'directory'
        else:
            require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= 128 * 1024**2)
            total += info.st_size;require(total <= MAX_BYTES)
            value = file_hash(path)
        digest.update((relative + '\0' + str(stat.S_IMODE(info.st_mode)) + '\0' + value + '\0').encode('utf-8'))
    return {'tree_sha256': digest.hexdigest(), 'file_count': len(paths), 'unpacked_bytes': total}


def validate_identity(value):
    require(type(value) is dict and set(value) == {'protocol', 'implementation', 'python_major',
        'python_minor', 'pypy_version', 'archive_sha256', 'executable_sha256', 'tree_sha256',
        'file_count', 'unpacked_bytes'})
    require(type(value['protocol']) is int and value['protocol'] == 1)
    require(value['implementation'] == 'pypy' and value['pypy_version'] == '8.0.1')
    require(type(value['python_major']) is int and value['python_major'] == 3
        and type(value['python_minor']) is int and value['python_minor'] == 11)
    require(value['archive_sha256'] == ARCHIVE_SHA256)
    require(all(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key])
        for key in ('executable_sha256', 'tree_sha256')))
    require(type(value['file_count']) is int and 0 < value['file_count'] <= MAX_ENTRIES)
    require(type(value['unpacked_bytes']) is int and 0 < value['unpacked_bytes'] <= MAX_BYTES)
    return value


def install():
    host();root_directory(ROOT.parent)
    require(not ROOT.exists() and not ROOT.is_symlink())
    require(shutil.disk_usage(ROOT.parent).free >= 20 * 1024**3 + MAX_ARCHIVE)
    ROOT.mkdir(mode=0o755)
    archive = ROOT / 'runtime.tar.gz';digest = hashlib.sha256();size = 0
    deadline = time.monotonic() + 120
    with urllib.request.urlopen(URL, timeout=30) as response, archive.open('xb') as output:
        while True:
            require(time.monotonic() < deadline)
            block = response.read(1024**2)
            if not block:break
            size += len(block);require(size <= MAX_ARCHIVE);digest.update(block);output.write(block)
    require(digest.hexdigest() == ARCHIVE_SHA256)
    with tarfile.open(archive, 'r:gz') as source:
        selected = members(source)
        planned = {str(item) for member in selected
            for item in (PurePosixPath(member.name), *PurePosixPath(member.name).parents) if str(item) != '.'}
        allocation = sum(member.size for member in selected if member.isreg()) + len(planned) * 8192 + 32 * 1024**2
        require(shutil.disk_usage(ROOT).free >= 20 * 1024**3 + allocation)
        source.extractall(ROOT, members=selected, filter='data')
    # Only this new checksum-verified tree is normalized; never another prefix.
    for path in (RUNTIME, *itertools.islice(RUNTIME.rglob('*'), MAX_ENTRIES + 1)):
        require(path.resolve(strict=True).is_relative_to(RUNTIME))
        if not path.is_symlink():path.chmod(stat.S_IMODE(path.stat().st_mode) & 0o755)
    require(EXECUTABLE.resolve(strict=True).is_relative_to(RUNTIME))
    smoke = ("import ctypes,hashlib,json,ssl,sys,time; "
        "assert sys.implementation.name=='pypy'; assert sys.version_info[:2]==(3,11); "
        "assert sys.pypy_version_info[:3]==(8,0,1); assert hasattr(hashlib,'file_digest'); "
        "assert ctypes.sizeof(ctypes.c_void_p)==8; time.process_time_ns(); time.thread_time_ns(); "
        "print('root-runtime-ready')")
    result = subprocess.run([str(EXECUTABLE), '-B', '-I', '-S', '-c', smoke],
        capture_output=True, timeout=30, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    require(result.returncode == 0 and result.stdout == b'root-runtime-ready\n' and len(result.stderr) <= 4096)
    value = validate_identity({'protocol': 1, 'implementation': 'pypy', 'python_major': 3,
        'python_minor': 11, 'pypy_version': '8.0.1', 'archive_sha256': ARCHIVE_SHA256,
        'executable_sha256': file_hash(EXECUTABLE), **tree_identity(RUNTIME)})
    with (ROOT / 'identity.json').open('x', encoding='utf-8') as output:json.dump(value, output, sort_keys=True)
    print(json.dumps({'diagnostic_only': True, 'production_runtime_adopted': False, **value}))


def observe():
    host();root_directory(ROOT)
    require(sys.implementation.name == 'pypy' and sys.version_info[:2] == (3, 11)
        and sys.pypy_version_info[:3] == (8, 0, 1))
    require(Path(sys.executable).resolve(strict=True) == EXECUTABLE.resolve(strict=True))
    path = ROOT / 'identity.json';info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
        and info.st_nlink == 1 and not info.st_mode & 0o022 and 0 < info.st_size <= 4096)
    value = validate_identity(json.loads(path.read_bytes()))
    require(file_hash(EXECUTABLE) == value['executable_sha256'])
    require(tree_identity(RUNTIME) == {key: value[key] for key in ('tree_sha256', 'file_count', 'unpacked_bytes')})
    return {'diagnostic_only': True, 'production_runtime_adopted': False,
        'cpython_guard_profile_supported': False, **value}


if __name__ == '__main__':
    require(sys.argv[1:] == ['--install']);install()
