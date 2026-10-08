"""Bounded external I/O. Forge authorization and records remain in Elixir."""
import http.client
import ipaddress
import json
import ssl
import sys
import urllib.parse

INPUT_LIMIT = 2_097_152
RESPONSE_LIMIT = 1_048_576


def emit(value):
    sys.stdout.buffer.write(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def valid_origin(parts, allow_loopback):
    if parts.username is not None or parts.password is not None:
        return False
    if parts.fragment or parts.scheme not in ("https", "http") or not parts.hostname:
        return False
    if parts.scheme == "https":
        return True
    if not allow_loopback:
        return False
    if parts.hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        return False


def main():
    connection = None
    try:
        raw = sys.stdin.buffer.read(INPUT_LIMIT + 1)
        if len(raw) > INPUT_LIMIT:
            emit({"error": "input_limit"})
            return
        request = json.loads(raw)
        parts = urllib.parse.urlsplit(request["url"])
        if not valid_origin(parts, request.get("allow_loopback_http") is True):
            emit({"error": "invalid_origin"})
            return
        method = request["method"]
        token = request["token"]
        if method not in ("GET", "POST") or not isinstance(token, str):
            emit({"error": "invalid_request"})
            return
        if not 16 <= len(token) <= 512 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            emit({"error": "invalid_request"})
            return
        headers = {"Accept": "application/json", "Authorization": "Bearer " + token}
        payload = request.get("payload")
        body = None
        if method == "POST":
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(body) > RESPONSE_LIMIT:
                emit({"error": "input_limit"})
                return
            headers["Content-Type"] = "application/json"
        elif payload is not None:
            emit({"error": "invalid_request"})
            return
        key = request.get("idempotency_key")
        if key is not None:
            if not isinstance(key, str) or not 1 <= len(key) <= 128 or any(
                not (c.isascii() and (c.isalnum() or c in "-_.")) for c in key
            ):
                emit({"error": "invalid_request"})
                return
            headers["Idempotency-Key"] = key
        if parts.scheme == "https":
            connection = http.client.HTTPSConnection(
                parts.hostname, parts.port, timeout=2, context=ssl.create_default_context()
            )
        else:
            connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=2)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        # http.client never follows redirects, even when a response names a new host.
        if 300 <= response.status < 400:
            emit({"error": "redirect_refused"})
            return
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            emit({"error": "encoding_refused"})
            return
        length = response.getheader("Content-Length")
        if length is not None and (not length.isascii() or not length.isdigit() or int(length) > RESPONSE_LIMIT):
            emit({"error": "response_limit"})
            return
        value = bytearray()
        while len(value) <= RESPONSE_LIMIT:
            chunk = response.read(min(16_384, RESPONSE_LIMIT + 1 - len(value)))
            if not chunk:
                break
            value.extend(chunk)
        if len(value) > RESPONSE_LIMIT:
            emit({"error": "response_limit"})
            return
        if length is not None and len(value) != int(length):
            emit({"error": "invalid_response"})
            return
        # No raw response, URL, headers or exception text enters a failure packet.
        parsed = json.loads(value.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        emit({"status": response.status, "body": parsed})
    except Exception:
        emit({"error": "unavailable"})
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()
