"""Single bounded Jev Decisions call. Parent enforces the total deadline.

Wire shape follows the locally documented Forge Decisions client; no Forge
runtime dependency. No tools, redirects, retries, or arbitrary endpoint.
"""
import json
import os
import sys
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError()
        payload = json.loads(raw)
        req = urllib.request.Request(
            "https://openrouter.ai/api/alpha/decisions", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["HARNESS_JEV_KEY"]},
            method="POST")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(req, timeout=5) as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError()
        response = json.loads(raw)
        answer = response["answers"]["interpretation"]
        if not isinstance(response.get("model"), str) or not response["model"]:
            raise ValueError()
        output = {"status": "complete", "answer": answer,
                  "model": response["model"], "provider_request_id": response.get("id")}
        encoded = json.dumps(output, allow_nan=False)
        if len(encoded.encode()) > 65536:
            raise ValueError()
        print(encoded)
    except urllib.error.HTTPError as exc:
        # No provider body or credential values enter logs or receipts.
        print(json.dumps({"status": "unavailable", "reason": "provider_http_" + str(exc.code)}))
    except Exception:
        print(json.dumps({"status": "unavailable", "reason": "provider_or_response_failure"}))


if __name__ == "__main__":
    main()
