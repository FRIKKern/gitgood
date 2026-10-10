"""Fixed protected entry for the ordinary generation observation stream."""
import os
from pathlib import Path
import stat
import sys


def main():
    try:
        directory = Path(__file__).parent
        if directory != Path('/opt/gitgood/native/v2'):
            raise ValueError('Unsupported installed generation monitor')
        for path in [Path(__file__), directory, *directory.parents]:
            value = path.lstat()
            if path.resolve(strict=True) != path or value.st_uid != 0 or value.st_mode & 0o022:
                raise ValueError('Installed generation monitor unavailable')
            if path == Path(__file__):
                if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
                    raise ValueError('Installed generation monitor unavailable')
            elif not stat.S_ISDIR(value.st_mode):
                raise ValueError('Installed generation monitor unavailable')
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(directory))
        # The imported guard is itself validated before importing its peers.
        entry = directory/'native_generation_admission_entry.py'; info = entry.lstat()
        if (entry.resolve(strict=True) != entry or info.st_uid != 0 or info.st_mode & 0o022
                or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
            raise ValueError('Installed import custody unavailable')
        from native_generation_admission_entry import trusted_modules
        trusted_modules(directory)
        from native_generation_monitor import main as monitor_main
        return monitor_main()
    except Exception:
        try:
            os.write(1, b'{"protocol":2,"status":"refused"}\n')
        except OSError:
            pass
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
