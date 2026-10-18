"""Probe: does DeepSeek accept an image together with response_format=json_object?

Usage:
    .venv/Scripts/python scripts/probe_vision.py [--no-json-mode]

Reads DEEPSEEK_API_KEY from the environment, or from a KEY=VALUE line in the
project's .env file. The key is never printed.
"""

from __future__ import annotations

import argparse
import base64
import asyncio
import io
import os
import sys
from pathlib import Path

from openai import AsyncOpenAI
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
PROMPT = 'Какого цвета квадрат? Ответь JSON {"color": "..."}'


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs into os.environ without overriding existing values."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def make_red_square_jpeg_b64() -> str:
    image = Image.new("RGB", (64, 64), (255, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


async def probe(use_json_mode: bool) -> int:
    load_env_file(ENV_FILE)
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print(
            "DEEPSEEK_API_KEY not set: export it or add DEEPSEEK_API_KEY=... to "
            f"{ENV_FILE}",
            file=sys.stderr,
        )
        return 2

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    image_b64 = make_red_square_jpeg_b64()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                },
            ],
        }
    ]
    kwargs: dict = {"model": model, "messages": messages}
    if use_json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    print(f"model={model} base_url={base_url} json_mode={use_json_mode}")
    try:
        response = await client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 - probe script reports any failure
        print(f"REQUEST FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    content = response.choices[0].message.content
    print("response:")
    print(content)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--no-json-mode",
        action="store_true",
        help="do not send response_format={'type': 'json_object'}",
    )
    args = parser.parse_args()
    return asyncio.run(probe(use_json_mode=not args.no_json_mode))


if __name__ == "__main__":
    sys.exit(main())
