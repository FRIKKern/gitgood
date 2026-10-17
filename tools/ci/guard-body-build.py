#!/usr/bin/env python3
"""Hosted-only compiler for the installed-code comparison; no product dependency."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig

from guard_body_source import MODULE_NAMES,header,select_sources

spec=importlib.util.spec_from_file_location('_guard_compiler_builder',Path(__file__).with_name('path-body-build.py'))
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
DIRECTIVES=builder.DIRECTIVES
WHEEL_SHA256=builder.WHEEL_SHA256
WHEEL_BYTES=builder.WHEEL_BYTES


def require(value):
    if not value:raise ValueError('Hosted installed body build invariant')


def main():
    require(sys.platform=='linux' and sys.version_info[:2]==(3,12) and sys.implementation.name=='cpython'
        and platform.machine()=='x86_64' and os.getuid()!=0
        and os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted')
    workspace=Path(__file__).resolve().parents[2];directory=workspace/'.gitgood/guard-body-probe'
    for output in {Path('/'),directory.parent.resolve()}:
        require(shutil.disk_usage(output).free-536870912>=20*1024**3)
    sources={name:(workspace/'tools/deployment'/(name+'.py')).read_bytes() for name in MODULE_NAMES}
    body,manifest=select_sources(sources)
    directory.mkdir(mode=0o755)
    vendor=builder.download_compiler(directory)
    for name,raw in sources.items():(directory/(name+'.py')).write_bytes(raw)
    source=directory/'guard-body-donor.pyx';generated=header()+body;source.write_text(generated,encoding='utf-8')
    c_source=directory/'guard-body-donor.c'
    environment={**os.environ,'PYTHONPATH':str(vendor),'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
    subprocess.run([sys.executable,'-B','-s','-c',
        'from Cython.Compiler.Main import setuptools_main; raise SystemExit(setuptools_main())',
        '--module-name','_guard_body_probe','-X',DIRECTIVES,'-o',str(c_source),str(source)],
        env=environment,check=True,timeout=120)
    require(0<c_source.stat().st_size<=33554432)
    suffix=sysconfig.get_config_var('EXT_SUFFIX');include=Path(sysconfig.get_path('include'))
    require(type(suffix) is str and '/' not in suffix and suffix.endswith('.so') and (include/'Python.h').is_file())
    extension=directory/('_guard_body_probe'+suffix)
    subprocess.run(['/usr/bin/cc','-shared','-fPIC','-O2','-std=c11','-fwrapv','-fno-strict-aliasing',
        '-Wall','-Wextra','-I'+str(include),str(c_source),'-o',str(extension)],check=True,timeout=180)
    require(0<extension.stat().st_size<=16777216)
    manifest.update(compiler_version='3.1.8',compiler_wheel_sha256=WHEEL_SHA256,
        compiler_wheel_bytes=WHEEL_BYTES,compiler_directives=DIRECTIVES,python_version=platform.python_version(),
        donor_source_sha256=hashlib.sha256(generated.encode()).hexdigest(),
        c_source_sha256=hashlib.sha256(c_source.read_bytes()).hexdigest(),
        elf_sha256=hashlib.sha256(extension.read_bytes()).hexdigest(),compiled=True,runtime_verified=False,
        production_adopted=False)
    (directory/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
