"""One-token local-gateway generation check; never prints credentials or response text."""
import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT.parent / "member2" / "config" / "cockpit-local.env"


def main():
    settings = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            settings[key.strip()] = value.strip().strip("\"'")
    api_key = settings.get("OPENAI_API_KEY")
    if not api_key:
        print(json.dumps({"ok": False, "error": "local gateway credential missing"}))
        return 1

    request_body = {
        "model": "gpt-6-luna",
        "messages": [{"role": "user", "content": "Reply only OK."}],
        "temperature": 0.7,
        "max_tokens": 8,
    }
    request = urllib.request.Request(
        "http://127.0.0.1:58329/v1/chat/completions",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=45) as response:
            result = json.load(response)
        usage = result.get("usage") or {}
        print(json.dumps({
            "ok": True,
            "http_status": 200,
            "requested_model": "gpt-6-luna",
            "returned_model": result.get("model"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "max_tokens": request_body["max_tokens"],
            "reasoning_effort_sent": False,
        }, ensure_ascii=False))
        return 0
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read().decode("utf-8", "replace"))
            message = ((error.get("error") or {}).get("message") or "")
            kind = (error.get("error") or {}).get("type") or (error.get("error") or {}).get("code")
        except Exception:
            message, kind = "", None
        # Keep only a short diagnostic; no request headers, key, or response payload.
        print(json.dumps({
            "ok": False,
            "http_status": exc.code,
            "error_type": kind,
            "error_message": message[:240],
        }, ensure_ascii=False))
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
