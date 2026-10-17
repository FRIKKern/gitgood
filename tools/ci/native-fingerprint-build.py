#!/usr/bin/env python3
"""Build only the disposable hosted diagnostic; never a product dependency."""
import os
from pathlib import Path
import subprocess
import sys
import sysconfig


def main():
    if (sys.platform != 'linux' or os.getuid() == 0 or
            os.environ.get('GITHUB_ACTIONS') != 'true' or
            os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'):
        raise RuntimeError('Disposable hosted diagnostic build required')
    directory = Path(__file__).resolve().parents[2] / '.gitgood/native-fingerprint-probe'
    directory.mkdir(mode=0o755)  # Refuse reuse of an earlier build.
    suffix = sysconfig.get_config_var('EXT_SUFFIX')
    include = Path(sysconfig.get_path('include'))
    if not suffix or not suffix.endswith('.so') or not (include / 'Python.h').is_file():
        raise RuntimeError('Matching CPython headers required')
    subprocess.run(['/usr/bin/cc', '-shared', '-fPIC', '-O2', '-std=c11',
        '-Wall', '-Wextra', '-Werror', '-I' + str(include),
        str(Path(__file__).with_name('native-fingerprint-probe.c')),
        '-o', str(directory / ('_fingerprint_probe' + suffix))], check=True, timeout=60)


if __name__ == '__main__':
    main()
