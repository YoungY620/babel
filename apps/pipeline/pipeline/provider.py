"""Small OpenAI HTTP client. Never put credential values in diagnostics."""
import http.client
import json
import os
import time
import urllib.error
import urllib.request


def request(path, payload=None, content_type="application/json"):
    body = payload if isinstance(payload, bytes) else (
        json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None)
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    for attempt in range(3):
        req = urllib.request.Request(base + "/" + path, data=body, headers={
            "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"].strip(),
            "Content-Type": content_type,
        })
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            try:
                code = json.loads(error.read()).get("error", {}).get("code")
            except (ValueError, AttributeError):
                code = None
            known = {"invalid_api_key", "insufficient_quota", "model_not_found", "permission_denied",
                     "rate_limit_exceeded", "unsupported_country_region_territory"}
            code = code if isinstance(code, str) and code in known else "unknown"
            if error.code not in (429, 500, 502, 503, 504) or code == "insufficient_quota" or attempt == 2:
                raise RuntimeError(f"Model provider returned HTTP {error.code} ({code}) for {path}") from None
            time.sleep(2 ** attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException):
            if attempt == 2:
                raise RuntimeError(f"Model provider connection failed for {path}") from None
            time.sleep(2 ** attempt)


def json_request(path, payload=None):
    return json.loads(request(path, payload))
