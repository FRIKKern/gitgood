"""Protected fixed installation entry for ownership publication admission."""
import os
from pathlib import Path
import stat
import sys


def main():
    try:
        directory = Path(__file__).parent
        if directory!=Path('/opt/gitgood/native/v2'):
            raise ValueError('Installed ownership entry unavailable')
        for path in [Path(__file__),directory,*directory.parents]:
            value = path.lstat()
            if path.resolve(strict=True)!=path or value.st_uid!=0 or value.st_mode&0o022:
                raise ValueError('Installed ownership entry unavailable')
            if path==Path(__file__):
                if not stat.S_ISREG(value.st_mode) or value.st_nlink!=1:
                    raise ValueError('Installed ownership entry unavailable')
            elif not stat.S_ISDIR(value.st_mode):
                raise ValueError('Installed ownership entry unavailable')
        sys.dont_write_bytecode = True
        sys.path.insert(0,str(directory))
        entry = directory/'native_generation_admission_entry.py'
        value = entry.lstat()
        if entry.resolve(strict=True)!=entry or value.st_uid!=0 or value.st_mode&0o022 or not stat.S_ISREG(value.st_mode) or value.st_nlink!=1:
            raise ValueError('Installed import custody unavailable')
        from native_generation_admission_entry import trusted_modules
        trusted_modules(directory)
        from native_ownership_publication import main as publication_main
        return publication_main()
    except Exception:
        try:
            os.write(1,b'{"protocol":3,"status":"refused"}\n')
        except OSError:
            pass
        return 1


if __name__=='__main__':
    raise SystemExit(main())
