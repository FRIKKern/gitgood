"""Retain only an interrupted first-install staging namespace; never execute its bytes."""
import json
import os
from pathlib import Path
import uuid

from native_inventory import directory_identity, private_bytes
from stage_native_artifact import publish_directory, sync_directory
from upgrade_journal import canonical, require, unique_object

PREFIX = "initial-staging-retention-"


def _load(custody, path, staging, partial):
    value = json.loads(private_bytes(path,16_384),object_pairs_hook=unique_object)
    require(isinstance(value,dict) and set(value) == {"protocol","purpose","record","operation","request_sha256","source","destination"})
    require(type(value["protocol"]) is int and value["protocol"] == 1 and value["purpose"] == "native_initial_staging_retention")
    require(isinstance(value["record"],str) and str(uuid.UUID(value["record"])) == value["record"])
    require(path.name == PREFIX + value["record"] + ".json")
    require(value["operation"] == custody.journal.operation and value["request_sha256"] == custody.inputs.request_sha256)
    source = value["source"]
    require(isinstance(source,dict) and set(source) == {"path","device","inode","uid"})
    require(source["path"] == str(partial) and all(type(source[key]) is int and source[key] >= 0 for key in ["device","inode","uid"]))
    require(source["uid"] == os.getuid())
    destination = staging / (".retained-initial-" + custody.journal.operation + "-" + value["record"] + ".partial")
    require(value["destination"] == str(destination))
    return value


def _apply(custody, value, staging):
    custody.owned({"stage"})
    source = Path(value["source"]["path"]); destination = Path(value["destination"])
    expected = {**value["source"],"path":str(destination)}
    if destination.exists() or destination.is_symlink():
        require(directory_identity(destination,private=True) == expected)
        # A subsequent attempt may now own a different partial at the original
        # path. This record grants no permission to adopt or modify that attempt.
        return
    require(directory_identity(source,private=True) == value["source"])
    publish_directory(source,destination)
    sync_directory(staging)
    require(directory_identity(destination,private=True) == expected)


def retain_initial_partial(custody):
    custody.owned({"stage"})
    require(custody.journal.record["completed"] == ["inspect"])
    staging = custody.inputs.root / "staging"
    require(directory_identity(staging,private=True) == custody.inputs.allocation["empty_directories"]["staging"])
    operation = custody.journal.operation
    target = staging / ("native-" + operation); partial = staging / (".native-" + operation + ".partial")
    require(not target.exists() and not target.is_symlink())
    paths = sorted(custody.directory.glob(PREFIX + "*.json")); require(len(paths) < 128)
    records = [_load(custody,path,staging,partial) for path in paths]
    try:
        for value in records: _apply(custody,value,staging)
        if partial.exists() or partial.is_symlink():
            source = directory_identity(partial,private=True)
            record = str(uuid.uuid4())
            destination = staging / (".retained-initial-" + operation + "-" + record + ".partial")
            value = {"protocol":1,"purpose":"native_initial_staging_retention","record":record,
                     "operation":operation,"request_sha256":custody.inputs.request_sha256,
                     "source":source,"destination":str(destination)}
            temporary = custody.directory / ("." + PREFIX + record + ".partial")
            with os.fdopen(custody.journal._open(temporary,os.O_WRONLY | os.O_CREAT | os.O_EXCL),"wb") as output:
                output.write(canonical(value) + b"\n"); output.flush(); os.fsync(output.fileno())
            custody.owned({"stage"})
            require(directory_identity(partial,private=True) == source)
            publish_directory(temporary,custody.directory / (PREFIX + record + ".json"))
            sync_directory(custody.directory)
            _apply(custody,value,staging); records.append(value)
    except BaseException:
        custody.usable = False
        raise
    custody.owned({"stage"})
    require(not partial.exists() and not partial.is_symlink())
    return {"retained_partials":[{"record":value["record"],"directory":{**value["source"],"path":value["destination"]}}
                                for value in records],
            "limitations":["Reserved interrupted first-install namespace only; retained bytes are neither adopted nor executed."]}
