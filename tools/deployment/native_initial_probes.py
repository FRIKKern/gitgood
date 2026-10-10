"""Fixed initial readiness and current owner access; no hidden verification repository."""
import hashlib
import http.cookiejar
import json
import ssl
import time
import urllib.error
import urllib.request

from native_edge import routing_profile
from native_probes import NoRedirect
from upgrade_journal import canonical, require, unique_object


class NativeInitialProbes:
    def __init__(self, actions, owner_id):
        require(type(owner_id) is int and owner_id > 0)
        self.actions = actions
        self.owner_id = owner_id
        self.profile = routing_profile(actions.configuration)
        context = ssl.create_default_context()
        context.load_verify_locations(cafile=str(actions.root / "configuration" / actions.configuration["edge"]["tls_certificate"]))
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}),
                         urllib.request.HTTPSHandler(context=context), urllib.request.HTTPCookieProcessor(self.cookies))

    def _owned(self):
        self.actions._owned({"verify", "activate", "enroll"})
        self.actions.reobserve()

    def _request(self, origin, path, *, method="GET", payload=None, headers=None):
        request = urllib.request.Request(origin + path, data=canonical(payload) if payload is not None else None,
                                          headers={"Accept":"application/json", **({"Content-Type":"application/json"} if payload is not None else {}), **(headers or {})}, method=method)
        try:
            with self.opener.open(request,timeout=5) as response:
                raw = response.read(1_048_577); require(len(raw) <= 1_048_576)
                return response.status, raw
        except urllib.error.HTTPError as error:
            code = error.code; error.close(); return code,b""

    def readiness(self, *, public=False):
        require(type(public) is bool); self._owned()
        origins = [self.profile["origin"]] if public else ["http://127.0.0.1:" + str(self.profile["ports"][name]) for name in ["forge","web"]]
        observations = []; deadline = time.monotonic() + 60
        for origin in origins:
            while True:
                try:
                    status,raw = self._request(origin,"/health/ready")
                    value = json.loads(raw,object_pairs_hook=unique_object) if status == 200 else {}
                    ready = value.get("candidate") == self.actions.inputs.intent["candidate"] and value.get("status") == "ready" and value.get("dirty") is False
                    require(value.get("operational_mode","active") == "active")
                    if value.get("service") == "gitgood-web": ready = ready and value.get("forge_candidate") == self.actions.inputs.intent["candidate"]
                    else:
                        checks = value.get("checks",{})
                        ready = ready and value.get("service") == "gitgood" and set(checks) == {"database","storage","artifact","executables","installation","ssh"} and all(check is True for check in checks.values())
                    if ready:
                        observations.append({"candidate":value["candidate"],"service":value["service"],"ready":True}); break
                except (OSError,ValueError): pass
                require(time.monotonic() < deadline); time.sleep(.2)
        self._owned()
        return observations

    def access(self):
        """Issue one bounded probe session, verify current owner access, then revoke it."""
        self.actions._owned({"activate","enroll"}); self._owned()
        ready = self.readiness(public=True); origin = self.profile["origin"]
        bootstrap = self.actions.inputs.inputs["bootstrap"]
        self.cookies.clear()
        status,_ = self._request(origin,"/api/repos"); require(status == 401)
        status,raw = self._request(origin,"/api/session",method="POST",payload={"username":bootstrap["username"],"password":bootstrap["password"]},headers={"Origin":origin})
        require(status == 200)
        session = json.loads(raw,object_pairs_hook=unique_object)
        require(isinstance(session,dict) and isinstance(session.get("csrf"),str) and len(session["csrf"]) == 43)
        try:
            cookies = list(self.cookies)
            require(len(cookies) == 1 and cookies[0].name == "gitgood_session" and cookies[0].secure and "HttpOnly" in cookies[0]._rest)
            user = session.get("user",{})
            require(user.get("username") == bootstrap["username"] and type(user.get("id")) is int and user["id"] == self.owner_id)
            require({"team":bootstrap["team"],"role":"owner"} in session.get("teams",[]))
            status,raw = self._request(origin,"/api/session"); require(status == 200)
            current = json.loads(raw,object_pairs_hook=unique_object)
            require(current.get("user") == user and {"team":bootstrap["team"],"role":"owner"} in current.get("teams",[]))
            status,raw = self._request(origin,"/api/teams/" + bootstrap["team"] + "/members"); require(status == 200)
            require({"username":bootstrap["username"],"role":"owner"} in json.loads(raw,object_pairs_hook=unique_object).get("members",[]))
            status,raw = self._request(origin,"/api/repos"); require(status == 200)
            require(isinstance(json.loads(raw,object_pairs_hook=unique_object).get("repositories"),list))
            result = {"candidate":self.actions.inputs.intent["candidate"],"initial_access_probe":True,
                      "ready":ready,"anonymous_private_api_denied":True,"owner_login_verified":True,
                      "current_owner_membership_verified":True,"authorized_repository_list_verified":True,
                      "limitations":["Initial readiness and access only; no repository is created and no complete J01/J02 Git workflow is claimed."]}
        finally:
            status,_ = self._request(origin,"/api/session",method="DELETE",headers={"Origin":origin,"x-gitgood-csrf":session["csrf"]})
            require(status == 200); self.cookies.clear()
        status,_ = self._request(origin,"/api/repos"); require(status == 401)
        self._owned(); result["probe_session_revoked"] = True
        return {**result,"receipt_sha256":hashlib.sha256(canonical(result)).hexdigest()}
