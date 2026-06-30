"""华严 OpenAI 兼容多模态客户端（豆包等）。"""

from __future__ import annotations

import base64
import logging

import requests

from backend.config import HUAYAN_API_BASE, HUAYAN_API_KEY

logger = logging.getLogger(__name__)


def _auth_header() -> dict[str, str]:
    if not HUAYAN_API_KEY:
        raise RuntimeError(
            "未配置 HUAYAN_API_KEY。请在 .env 填入华严 API Key（格式 sk-xxx）"
        )
    key = HUAYAN_API_KEY.strip()
    if not key.startswith("Bearer "):
        key = f"Bearer {key}"
    return {"Authorization": key, "Content-Type": "application/json"}


def _image_to_data_url(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def chat_vision(
    *,
    model: str,
    prompt: str,
    image_bytes: bytes,
    mime: str = "image/jpeg",
    max_tokens: int = 4096,
    temperature: float = 0.1,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": _image_to_data_url(image_bytes, mime)},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_completion_tokens": max_tokens,
        "temperature": temperature,
    }
    # 豆包系列需关闭 thinking；Gemini 等模型不传该字段
    if model.startswith("doubao"):
        payload["thinking"] = {"type": "disabled"}

    url = f"{HUAYAN_API_BASE.rstrip('/')}/chat/completions"
    resp = requests.post(url, headers=_auth_header(), json=payload, timeout=180)
    if not resp.ok:
        logger.error("华严 VLM HTTP %s: %s", resp.status_code, resp.text[:500])
        raise RuntimeError(f"华严 VLM 调用失败 [{resp.status_code}]: {resp.text[:500]}")

    data = resp.json()
    message = data["choices"][0]["message"]
    content = message.get("content") or ""
    logger.debug("华严 VLM 响应 model=%s len=%s chars", model, len(content))
    return content
