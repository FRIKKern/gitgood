"""Installed fixed entry; isolated Python loads only its Root-controlled directory."""
import itertools
import os
from pathlib import Path
import stat
import sys


def trusted_modules(directory):
    paths = list(itertools.islice(directory.iterdir(), 129))
    if not 2 <= len(paths) <= 128:
        raise ValueError("Installed admission modules unavailable")
    names = set()
    for path in paths:
        info = path.lstat()
        if (path.resolve(strict=True) != path or info.st_uid != 0 or
                info.st_mode & 0o022 or not stat.S_ISREG(info.st_mode) or
                info.st_nlink != 1 or not 0 < info.st_size <= 1024 * 1024 or
                path.suffix not in {".py", ".ex", ".exs"}):
            raise ValueError("Installed admission modules unavailable")
        names.add(path.name)
    if not {"native_generation_admission_entry.py", "native_generation_admission.py",
            "native_generation_reader.py", "native_service_scope.py"} <= names:
        raise ValueError("Installed admission modules unavailable")


def main():
    try:
        directory = Path(__file__).parent
        if directory != Path("/opt/gitgood/native/v2"):
            raise ValueError("Unsupported installed admission entry")
        for path in [Path(__file__), directory, *directory.parents]:
            value = path.lstat()
            if path.resolve(strict=True) != path or value.st_uid != 0 or value.st_mode & 0o022:
                raise ValueError("Installed admission entry unavailable")
            if path == Path(__file__):
                if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
                    raise ValueError("Installed admission entry unavailable")
            elif not stat.S_ISDIR(value.st_mode):
                raise ValueError("Installed admission entry unavailable")
        trusted_modules(directory)
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(directory))
        from native_generation_admission import main as admitted_main
        return admitted_main()
    except Exception:
        os.write(1, b'{"protocol":2,"status":"refused"}\n')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
