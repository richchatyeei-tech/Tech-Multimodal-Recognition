"""千帆视觉理解（多模态）客户端。"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import requests

from backend.config import QIANFAN_API_KEY

logger = logging.getLogger(__name__)

CHAT_URL = "https://qianfan.baidubce.com/v2/chat/completions"


def _auth_header() -> dict[str, str]:
    if not QIANFAN_API_KEY:
        raise RuntimeError(
            "未配置 QIANFAN_API_KEY。请在 .env 中填入千帆控制台创建的 API Key"
            "（格式 bce-v3/ALTAK-xxx/xxx，与 OCR 的 AK/SK 不同）。"
        )
    key = QIANFAN_API_KEY.strip()
    if not key.startswith("Bearer "):
        key = f"Bearer {key}"
    return {"Authorization": key, "Content-Type": "application/json"}


def image_to_data_url(image_bytes: bytes, mime: str = "image/jpeg") -> str:
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
                        "image_url": {"url": image_to_data_url(image_bytes, mime)},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_completion_tokens": max_tokens,
        "temperature": temperature,
    }

    resp = requests.post(
        CHAT_URL,
        headers=_auth_header(),
        json=payload,
        timeout=180,
    )
    if not resp.ok:
        logger.error("千帆 VLM HTTP %s: %s", resp.status_code, resp.text[:500])
        raise RuntimeError(f"千帆 VLM 调用失败 [{resp.status_code}]: {resp.text[:500]}")

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    logger.debug("千帆 VLM 响应 model=%s len=%s chars", model, len(content))
    return content


def extract_json_from_text(text: str) -> dict[str, Any]:
    """从模型输出中提取 JSON。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise RuntimeError(f"无法解析模型 JSON 输出: {text[:300]}")
