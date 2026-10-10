"""Publish the first current-release pointer under initial installation custody."""
import hashlib
import os
import uuid

from native_activation import NativeActivation
from native_inventory import directory_identity, private_bytes
from stage_native_artifact import publish_directory, sync_directory
from upgrade_journal import canonical, require


def activate_initial(actions, schema, public_probe):
    actions._owned({"activate"}); actions.reobserve()
    verified = actions._stage(actions.directory)
    require(schema == verified["migrations"])
    require(isinstance(public_probe,dict) and public_probe.get("candidate") == actions.inputs.intent["candidate"] and
            public_probe.get("initial_access_probe") is True and isinstance(public_probe.get("receipt_sha256"),str))
    value = NativeActivation.validate({"protocol":1,"installation":actions.inputs.intent["installation"],
             "operation":actions.journal.operation,"candidate":actions.inputs.intent["candidate"],
             "artifact_sha256":actions.inputs.intent["artifact_sha256"],"bindings_sha256":actions.inputs.allocation["bindings_sha256"],
             "stage":directory_identity(actions.directory,private=True),"stage_inventory_sha256":verified["inventory_sha256"],
             "schema":schema,"public_probe_sha256":public_probe["receipt_sha256"]})
    raw = canonical(value) + b"\n"; path = actions.custody.directory / "current-release-v1.json"
    if path.exists() or path.is_symlink():
        require(private_bytes(path,16_384) == raw)
        return {"record":value,"sha256":hashlib.sha256(raw).hexdigest()}
    temporary = actions.custody.directory / (".initial-current-release-" + str(uuid.uuid4()) + ".partial")
    try:
        with os.fdopen(actions.journal._open(temporary,os.O_WRONLY | os.O_CREAT | os.O_EXCL),"wb") as target:
            target.write(raw); target.flush(); os.fsync(target.fileno())
        actions._owned({"activate"}); actions.reobserve()
        publish_directory(temporary,path); sync_directory(actions.custody.directory)
    except BaseException:
        actions.custody.usable = False
        raise
    require(private_bytes(path,16_384) == raw)
    return {"record":value,"sha256":hashlib.sha256(raw).hexdigest()}
