"""多厂商 VLM 统一入口。"""

from __future__ import annotations

import logging

from backend.clients import huayan_vlm, qianfan_vlm
from backend.config import get_model_spec

logger = logging.getLogger(__name__)

# 复用 JSON 解析
extract_json_from_text = qianfan_vlm.extract_json_from_text


def chat_vision(
    *,
    model: str,
    prompt: str,
    image_bytes: bytes,
    mime: str = "image/jpeg",
    max_tokens: int = 4096,
    temperature: float = 0.1,
) -> str:
    spec = get_model_spec(model)
    provider = spec["provider"]
    logger.debug("VLM 路由 model=%s provider=%s", model, provider)

    if provider == "qianfan":
        return qianfan_vlm.chat_vision(
            model=model,
            prompt=prompt,
            image_bytes=image_bytes,
            mime=mime,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    if provider == "huayan":
        return huayan_vlm.chat_vision(
            model=model,
            prompt=prompt,
            image_bytes=image_bytes,
            mime=mime,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    raise RuntimeError(f"未实现的 VLM 厂商: {provider}")
