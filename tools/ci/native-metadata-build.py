#!/usr/bin/env python3
"""Build the finite metadata diagnostic only on a disposable hosted runner."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig

FLAGS = ('-shared','-fPIC','-O2','-std=c11','-Wall','-Wextra','-Werror')


def main():
    if not (sys.platform=='linux' and sys.version_info[:2]==(3,12) and os.getuid()!=0
            and os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'):
        raise RuntimeError('Disposable hosted metadata build required')
    directory=Path(__file__).resolve().parents[2]/'.gitgood/native-metadata-probe'
    for output in {Path('/'),directory.parent.resolve()}:
        if shutil.disk_usage(output).free-67108864<20*1024**3:
            raise RuntimeError('Metadata diagnostic reserve unavailable')
    include=Path(sysconfig.get_path('include'));suffix=sysconfig.get_config_var('EXT_SUFFIX')
    if not suffix or '/' in suffix or not suffix.endswith('.so') or not (include/'Python.h').is_file():
        raise RuntimeError('Matching CPython headers required')
    directory.mkdir(mode=0o755)
    source=Path(__file__).with_name('native-metadata-probe.c');extension=directory/('_native_metadata_probe'+suffix)
    subprocess.run(['/usr/bin/cc',*FLAGS,
        '-I'+str(include),str(source),'-o',str(extension)],check=True,timeout=60)
    if not 0<extension.stat().st_size<=16777216:raise RuntimeError('Metadata extension size bound')
    manifest={'protocol':1,'compiler':'system-cc','compiler_flags':list(FLAGS),'python_version':platform.python_version(),
        'c_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'elf_sha256':hashlib.sha256(extension.read_bytes()).hexdigest(),'production_adopted':False}
    (directory/'manifest.json').write_text(json.dumps(manifest,sort_keys=True)+'\n',encoding='utf-8')


if __name__=='__main__':main()
