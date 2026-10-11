"""Observe absence of one retained backend identity, without signalling or leasing."""
import json
import subprocess

from native_durable_database import SQL, DatabaseRefused, unique, validate_database
from native_inventory import database_environment
from native_ownership_database import OBSERVATION_OPTIONS, _query_database, validate_session


def require(value):
    if not value:
        raise DatabaseRefused('Original native database backend absence unavailable')


def observe_prior_backend_absence(psql, database_url, snapshot, expected_database):
    """A controller must separately prove owner/descendant absence and exclusion.

    Database identity must remain independently admitted. A visible reused PID
    with a different birth establishes only the retained backend's absence; its
    current process is never signalled, adopted or returned as authority.
    """
    try:
        environment=database_environment(database_url)
        environment.update(PGPASSFILE='/dev/null',PGOPTIONS=OBSERVATION_OPTIONS)
        validate_database(expected_database,environment)
        validate_session(snapshot,expected_database)
        statement="SELECT json_build_object('database',("+SQL.strip().rstrip(';')+")," \
            "'backend',(SELECT json_build_object('pid',pid," \
            "'birth',floor(extract(epoch FROM backend_start)*1000000)::bigint::text)" \
            " FROM pg_stat_activity WHERE pid="+str(snapshot['backend_pid'])+"))"
        observed=json.loads(_query_database(psql,environment,statement),object_pairs_hook=unique)
        require(type(observed) is dict and set(observed)=={'database','backend'})
        require(observed['database']==expected_database)
        validate_database(observed['database'],environment)
        backend=observed['backend']
        reused=False
        if backend is not None:
            require(type(backend) is dict and set(backend)=={'pid','birth'})
            current={'database':expected_database,'backend_pid':backend['pid'],'backend_birth':backend['birth']}
            validate_session(current,expected_database)
            require(current['backend_pid']==snapshot['backend_pid'])
            require(current['backend_birth']!=snapshot['backend_birth'])
            reused=True
        return {'original_backend_absent':True,'backend_activity_absence_observed':True,
                'kernel_backend_absence_observed':False,'pid_reused':reused,'expected_database_observed':True,
                'lease_acquired':False,'writer_exclusion_established':False,
                'owner_process_absence_observed':False,'descendant_absence_observed':False}
    except (DatabaseRefused,OSError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,subprocess.SubprocessError):
        raise DatabaseRefused('Original native database backend absence unavailable') from None
