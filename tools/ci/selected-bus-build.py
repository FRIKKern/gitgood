#!/usr/bin/env python3
"""Build small diagnostic DSOs only on a disposable hosted Linux runner."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig


def main():
    if (sys.platform != 'linux' or os.getuid() == 0 or sys.implementation.name != 'cpython'
            or os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'):
        raise RuntimeError('Disposable hosted CPython build required')
    source = Path(__file__).resolve().parent
    destination = source.parents[1] / '.gitgood/selected-bus-probe'
    # Includes compiler temporaries and both tiny outputs; no local builds.
    for path in {Path('/'), destination.parent.resolve()}:
        if shutil.disk_usage(path).free - 16 * 1024**2 < 20 * 1024**3:
            raise RuntimeError('Hosted build reserve unavailable')
    suffix = sysconfig.get_config_var('EXT_SUFFIX');include = Path(sysconfig.get_path('include'))
    if not suffix or not suffix.endswith('.so') or not (include / 'Python.h').is_file():
        raise RuntimeError('Matching CPython headers required')
    destination.mkdir(mode=0o755)  # Refuse an earlier build.
    flags = ['/usr/bin/cc','-shared','-fPIC','-O2','-std=c11','-Wall','-Wextra','-Werror']
    subprocess.run([*flags,'-I'+str(include),str(source/'selected-bus-probe.c'),'-ldl',
        '-o',str(destination/('_selected_bus_probe'+suffix))],check=True,timeout=60)
    subprocess.run([*flags,str(source/'selected-bus-fixture.c'),'-o',
        str(destination/'selected-bus-fixture.so')],check=True,timeout=60)


if __name__ == '__main__':main()
