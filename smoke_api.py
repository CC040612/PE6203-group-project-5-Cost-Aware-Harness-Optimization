"""手动运行的 API 接入检查；不属于自动单元测试。"""
import argparse
import json
import os

import httpx
from openai import OpenAI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-6-luna")
    args = parser.parse_args()

    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise SystemExit("请先通过环境变量设置 OPENAI_API_KEY。")

    base_url = os.environ.get(
        "OPENAI_BASE_URL", "http://172.26.240.1:64915/v1"
    )

    with OpenAI(
        base_url=base_url,
        api_key=key,
        http_client=httpx.Client(trust_env=False),
        timeout=90,
        max_retries=0,
    ) as client:
        response = client.chat.completions.create(
            model=args.model,
            messages=[{"role": "user", "content": "Reply with exactly OK."}],
            max_tokens=128,
        )

    print(json.dumps({
        "requested_model": args.model,
        "returned_model": response.model,
        "reply": response.choices[0].message.content,
        "usage": response.usage.model_dump() if response.usage else None,
  

    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
