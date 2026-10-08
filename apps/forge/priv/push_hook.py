"""Narrow Git-to-Elixir callback; the backend alone decides whether refs may change."""
import json
import os
import sys
import urllib.request
import urllib.parse

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def main():
    body = sys.stdin.buffer.read(65537)
    if len(body) > 65536:
        return 1
    url = os.environ["GITGOOD_INTERNAL_URL"] + "/internal/pushes/" + os.environ["GITGOOD_PUSH_ID"]
    if urllib.parse.urlsplit(url).hostname != "127.0.0.1":
        return 1
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + os.environ["GITGOOD_HOOK_TOKEN"],
        "Content-Type": "application/x-gitgood-ref-updates"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=15) as result:
        if result.status != 200 or json.loads(result.read(4096)).get("allowed") is not True:
            return 1
    return 0
if __name__ == "__main__":
    try:
        status = main()
    except Exception:
        status = 1
    if status:
        sys.stderr.write("Gitgood refused these ref updates. Check access and branch policy.\n")
    sys.exit(status)
