"""Installed fixed entry; isolated Python loads only its Root-controlled directory."""
import itertools
import os
from pathlib import Path
import stat
import sys

REQUIRED_MODULES = frozenset({
    'enrollment_journal.py', 'generation_custody.py', 'generation_publication.py',
    'inspect_native_artifact.py', 'native_actions.py', 'native_artifact_controller.py', 'native_backend_observation.py',
    'native_backend_observation_entry.py', 'native_backend_scope.py', 'native_command_wire.py', 'native_command_endpoint.py',
    'native_controller_scope.py', 'native_durable_binding.py', 'native_durable_database.py',
    'native_generation_admission.py', 'native_generation_admission_entry.py',
    'native_generation_lease_guard.py', 'native_generation_monitor.py',
    'native_generation_monitor_entry.py', 'native_generation_reader.py', 'native_inventory.py',
    'native_kernel_backend.py', 'native_lifecycle_business_inputs.py', 'native_lifecycle_generation_reader.py',
    'native_lifecycle_history.py', 'native_lifecycle_responsibility.py',
    'native_lifecycle_worker_inputs.py', 'native_monitor_ownership_attachment.py', 'native_monitor_business_inputs.py',
    'native_operation_inputs.py', 'native_public_runtime.py', 'native_ownership_database.py', 'native_ownership_marker_guard.py',
    'native_ownership_markers.py', 'native_ownership_observation.py',
    'native_ownership_publication.py', 'native_ownership_publication_entry.py',
    'native_ownership_records.py', 'native_prior_backend.py', 'native_root_artifact_dispatch.py', 'native_root_artifact_policy.py', 'native_root_controller.py', 'native_root_controller_request.py', 'native_root_database_exclusion.py', 'native_root_lifecycle.py', 'native_root_live_binding.py', 'native_service_scope.py',
    'native_root_database_reader.py', 'native_ownership_controller.py', 'native_ownership_transition.py',
    'native_ownership_handoff.py', 'native_ownership_handoff_entry.py',
    'native_systemd_properties.py', 'native_worker_scope.py', 'native_writer_exclusion.py',
    'resource_generations.py', 'stage_native_artifact.py', 'upgrade_journal.py',
})


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
    if not REQUIRED_MODULES <= names:
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
