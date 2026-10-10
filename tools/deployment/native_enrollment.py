"""Fixed first-install coordinator; historical completion never asserts fresh readiness."""
import hashlib
import json
import os
from pathlib import Path
import uuid

from enrollment_journal import ERRORS, STAGES
from initial_staging_retention import retain_initial_partial
from native_edge import start_edge
from native_enrollment_actions import NativeEnrollmentActions
from native_enrollment_custody import NativeEnrollmentCustody
from native_enrollment_inputs import NativeEnrollmentInputs
from native_initial_activation import activate_initial
from native_initial_baseline import read_initial_baseline, seal_initial_baseline
from native_initial_probes import NativeInitialProbes
from native_initial_observations import completed_observation
from native_inventory import private_bytes
from stage_native_artifact import publish_directory, sync_directory
from upgrade_journal import canonical, require, unique_object


class NativeEnrollment:
    def __init__(self, inputs_directory, request_sha256):
        self.inputs = NativeEnrollmentInputs(inputs_directory,request_sha256)

    def _receipt(self, custody, stage, result, *, observation=False):
        custody.owned({stage},observation=observation)
        require(isinstance(result,dict))
        value = {"protocol":1,"purpose":"native_initial_stage_observation","operation":custody.journal.operation,
                 "request_sha256":self.inputs.request_sha256,"stage":stage,"result":result}
        raw = canonical(value) + b"\n"; require(len(raw) <= 131_072)
        digest = hashlib.sha256(raw).hexdigest()
        path = custody.directory / ("enrollment-observation-" + digest + ".json")
        if path.exists() or path.is_symlink():
            require(private_bytes(path,131_072) == raw)
        else:
            temporary = custody.directory / (".enrollment-observation-" + str(uuid.uuid4()) + ".partial")
            try:
                with os.fdopen(custody.journal._open(temporary,os.O_WRONLY | os.O_CREAT | os.O_EXCL),"wb") as output:
                    output.write(raw); output.flush(); os.fsync(output.fileno())
                custody.owned({stage},observation=observation); publish_directory(temporary,path); sync_directory(custody.directory)
            except BaseException:
                custody.usable = False
                raise
        return {"receipt_sha256":digest}

    def _completed(self, custody, stage):
        return completed_observation(custody.journal, stage)

    def run(self):
        return self._execute(repair=False)

    def resume(self):
        return self._execute(repair=True)

    def _quiesce(self,custody):
        # Narrow whole-group shutdown remains possible when database observation
        # is unavailable. The sealed scope and current kernel identities govern
        # this operation; no database, archive or stale process name is adopted.
        actions = NativeEnrollmentActions.__new__(NativeEnrollmentActions)
        actions.custody = custody; actions.inputs = self.inputs; actions.journal = custody.journal
        actions.root = self.inputs.root; actions.bindings = self.inputs.allocation["bindings"]
        return {name:actions.stop_group(name,observation=True) for name in ["edge","web","native","maintenance"]}

    def _observe(self,actions,stage):
        if stage == "inspect": return True,actions.inspect(observation=True)
        if stage == "stage":
            path = actions.directory
            if not path.exists() and not path.is_symlink():
                return False,{"published_stage_absent":True,"partial_bytes_not_adopted":True}
            actions._stage(path)
            value = json.loads(private_bytes(path / "receipt.json",16_384),object_pairs_hook=unique_object)
            require(isinstance(value,dict) and set(value) == {"protocol","status","operation","candidate","artifact_sha256","artifact_bytes","inventory_sha256","files","symlinks","migrations","limitations"})
            require(type(value["protocol"]) is int and value["protocol"] == 1 and value["operation"] == actions.journal.operation)
            return True,value
        if stage == "migrate":
            verified = actions._stage(actions.directory)
            schema = actions.initial_schema(observation=True)
            require(verified["migrations"][:len(schema)] == schema)
            return schema == verified["migrations"],{"migration_effect_observed":True,"schema":schema,"inventory_sha256":verified["inventory_sha256"]}
        if stage == "bootstrap":
            value = actions.bootstrap(observe=True)
            return value["outcome"] == "recorded",value
        # Runtime verification and routing are repeatable only after exact
        # whole-group quiescence, artifact checks and a fresh functional probe.
        return False,{"runtime_groups_quiescent":True,"fresh_stage_verification_required":True}

    def _execute(self, *, repair):
        require(type(repair) is bool)
        with NativeEnrollmentCustody(self.inputs) as custody:
            journal = custody.journal
            if journal.record["status"] == "complete":
                baseline = seal_initial_baseline(custody)
                return {"protocol":1,"purpose":"native_initial_enrollment","outcome":"recorded_complete",
                        "installation":self.inputs.intent["installation"],"operation":journal.operation,
                        "candidate":self.inputs.intent["candidate"],"status":"complete",
                        "baseline_sha256":hashlib.sha256(canonical(baseline) + b"\n").hexdigest(),
                        "limitations":["Recorded terminal responsibility and metadata handoff only; no fresh login, routing or readiness observation."]}
            require(journal.record["status"] in ({"pending","failed","uncertain"} if repair else {"pending"}))
            for stage in journal.record["completed"]: self._completed(custody,stage)
            actions = None
            prestarted = None
            repaired_stage = None
            try:
                if repair and journal.record["status"] in {"failed","uncertain"}:
                    self._quiesce(custody)
                    actions = NativeEnrollmentActions(custody)
                    stage = journal.record["stage"]
                    applied,result = self._observe(actions,stage)
                    if journal.record["status"] == "uncertain":
                        journal.reconcile(applied=applied,evidence=self._receipt(custody,stage,result,observation=True))
                    elif applied:
                        journal.begin(stage); journal.succeed(stage,self._receipt(custody,stage,result))
                    repaired_stage = stage
                elif repair and journal.record["completed"]:
                    prestarted = STAGES[len(journal.record["completed"])]
                    journal.begin(prestarted)
                    self._quiesce(custody)
                    repaired_stage = prestarted
                actions = NativeEnrollmentActions(custody)
                for stage in STAGES[len(journal.record["completed"]):]:
                    if stage != prestarted: journal.begin(stage)
                    if stage == "inspect": result = actions.inspect()
                    elif stage == "stage":
                        retained = retain_initial_partial(custody) if repaired_stage == "stage" else None
                        result = actions.stage()
                        if retained is not None: result = {**result,"retention":retained}
                    elif stage == "migrate": result = actions.migrate(resume=repaired_stage == "migrate")
                    elif stage == "bootstrap": result = actions.bootstrap()
                    else:
                        owner = self._completed(custody,"bootstrap")
                        require(owner.get("outcome") in {"created","recorded"})
                        probes = NativeInitialProbes(actions,owner["user_id"])
                        if stage == "verify":
                            actions.start_native(); actions.start_web()
                            schema = actions.schema(); require(schema == actions._stage(actions.directory)["migrations"])
                            result = {"schema":schema,"internal_readiness":probes.readiness()}
                        elif stage == "activate":
                            if repaired_stage == "activate":
                                actions.start_native(); actions.start_web(); probes.readiness()
                            start_edge(actions,"active",initial=True)
                            public = probes.access(); schema = actions.schema()
                            pointer = activate_initial(actions,schema,public)
                            result = {"pointer_sha256":pointer["sha256"],"schema":schema,"public_access":public}
                        else:
                            if repaired_stage == "enroll":
                                actions.start_native(); actions.start_web(); probes.readiness(); start_edge(actions,"active",initial=True)
                            activated = self._completed(custody,"activate")
                            raw = private_bytes(custody.directory / "current-release-v1.json",16_384)
                            require(hashlib.sha256(raw).hexdigest() == activated["pointer_sha256"])
                            public = probes.access(); schema = actions.schema()
                            require(schema == activated["schema"] == actions._stage(actions.directory)["migrations"])
                            result = {"pointer_sha256":activated["pointer_sha256"],"schema":schema,"public_access":public}
                    journal.succeed(stage,self._receipt(custody,stage,result))
                baseline = seal_initial_baseline(custody)
                final = self._completed(custody,"enroll")
                require(read_initial_baseline(custody.directory) == baseline)
                return {"protocol":1,"purpose":"native_initial_enrollment","outcome":"enrolled",
                        "installation":self.inputs.intent["installation"],"operation":journal.operation,
                        "candidate":self.inputs.intent["candidate"],"status":"complete","schema":final["schema"],
                        "verification":{"initial_access_probe":True,"probe_session_revoked":True,"pointer_sha256":final["pointer_sha256"]},
                        "limitations":["Same-boot preallocated native host only; no host allocator, reboot supervision or managed Cloud acceptance.",
                                       "Initial readiness/owner access only; complete J01/J02 Git workflows and J14 acceptance require separate current evidence."]}
            except BaseException:
                if actions is not None and custody.usable and journal.usable and journal.record["status"] == "running":
                    quiescent = True
                    for name in ["edge","web","native","maintenance"]:
                        try: actions.stop_group(name)
                        except Exception: quiescent = False
                    if quiescent:
                        journal.fail(ERRORS[journal.record["stage"]])
                raise
