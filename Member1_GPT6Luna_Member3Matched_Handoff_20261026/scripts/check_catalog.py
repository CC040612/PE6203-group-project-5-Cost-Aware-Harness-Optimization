"""Check the local gateway's model catalog without generating text."""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    settings = {}
    for line in (ROOT.parent / 'member2/config/cockpit-local.env').read_text(encoding='utf-8').splitlines():
        if line.strip() and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            settings[key] = value.strip().strip('\"\'')
    base = 'http://127.0.0.1:58329/v1' if os.name == 'nt' else 'http://127.0.0.1:58429/v1'
    request = urllib.request.Request(base + '/models', headers={'Authorization': 'Bearer ' + settings['OPENAI_API_KEY']})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=30) as response:
        catalog = json.load(response)
    models = [m.get('id', m.get('slug')) for m in catalog.get('data', catalog.get('models', []))]
    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'model_requested': 'gpt-6-luna',
              'found': 'gpt-6-luna' in models, 'models': models, 'generation_requests': 0}
    (ROOT / 'config/model-catalog.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['found'] else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except urllib.error.HTTPError as exc:
        print(f'Local gateway catalog HTTP {exc.code}; no generation requests.', file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f'Local gateway catalog unavailable ({type(exc).__name__}); no generation requests.', file=sys.stderr)
        sys.exit(1)
