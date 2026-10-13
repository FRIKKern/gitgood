"""Fixed protected ownership handoff entry; no caller-selected code or endpoint."""
import os
from pathlib import Path
import stat
import sys


def main():
    try:
        directory=Path(__file__).parent
        if directory!=Path('/opt/gitgood/native/v2'):raise ValueError('Installed handoff unavailable')
        for path in [Path(__file__),directory,*directory.parents]:
            info=path.lstat()
            if path.resolve(strict=True)!=path or info.st_uid!=0 or info.st_mode&0o022:
                raise ValueError('Installed handoff unavailable')
            if path==Path(__file__):
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('Installed handoff unavailable')
            elif not stat.S_ISDIR(info.st_mode):raise ValueError('Installed handoff unavailable')
        sys.dont_write_bytecode=True;sys.path.insert(0,str(directory))
        entry=directory/'native_generation_admission_entry.py';info=entry.lstat()
        if entry.resolve(strict=True)!=entry or info.st_uid!=0 or info.st_mode&0o022 or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            raise ValueError('Installed handoff unavailable')
        from native_generation_admission_entry import trusted_modules
        trusted_modules(directory)
        from native_ownership_handoff import main as handoff_main
        return handoff_main()
    except Exception:
        try:os.write(1,b'{"protocol":4,"status":"refused"}\n')
        except OSError:pass
        return 1


if __name__=='__main__':raise SystemExit(main())
