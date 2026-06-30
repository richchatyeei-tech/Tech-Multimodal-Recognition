"""百度 OCR 试卷切题客户端。"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import requests

from backend.config import BAIDU_OCR_AK, BAIDU_OCR_SK

logger = logging.getLogger(__name__)

TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
CREATE_TASK_URL = (
    "https://aip.baidubce.com/rest/2.0/ocr/v1/paper_cut_edu_vlm/create_task"
)

_token_cache: dict[str, Any] = {}


def _get_access_token() -> str:
    if _token_cache.get("expires_at", 0) > time.time() + 60:
        logger.debug("复用缓存 OCR access_token")
        return _token_cache["token"]

    logger.info("请求新的 OCR access_token …")
    resp = requests.get(
        TOKEN_URL,
        params={
            "grant_type": "client_credentials",
            "client_id": BAIDU_OCR_AK,
            "client_secret": BAIDU_OCR_SK,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"获取 OCR access_token 失败: {data}")

    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + int(data.get("expires_in", 2592000))
    logger.info("OCR access_token 获取成功，有效期 %ss", data.get("expires_in", "?"))
    return data["access_token"]


def coord_to_box(coord: list[float]) -> dict[str, float]:
    """[x1,y1,x2,y2] → {x,y,w,h}"""
    x1, y1, x2, y2 = coord
    return {
        "x": round(min(x1, x2), 2),
        "y": round(min(y1, y2), 2),
        "w": round(abs(x2 - x1), 2),
        "h": round(abs(y2 - y1), 2),
    }


def _item_to_box(item: dict) -> dict[str, float] | None:
    """支持官方 {x,y,w,h} 与旧版 coordinate [x1,y1,x2,y2] 两种格式。"""
    if all(k in item for k in ("x", "y", "w", "h")):
        return {
            "x": round(float(item["x"]), 2),
            "y": round(float(item["y"]), 2),
            "w": round(float(item["w"]), 2),
            "h": round(float(item["h"]), 2),
            "score": item.get("score"),
        }
    coord = item.get("coordinate")
    if coord and len(coord) >= 4:
        box = coord_to_box(coord)
        box["score"] = item.get("score")
        return box
    return None


def _parse_location_items(items: list[dict] | None) -> list[dict]:
    if not items:
        return []
    boxes = []
    for item in items:
        box = _item_to_box(item)
        if box:
            boxes.append(box)
    return boxes


def _union_box(boxes: list[dict]) -> dict[str, float] | None:
    if not boxes:
        return None
    x1 = min(b["x"] for b in boxes)
    y1 = min(b["y"] for b in boxes)
    x2 = max(b["x"] + b["w"] for b in boxes)
    y2 = max(b["y"] + b["h"] for b in boxes)
    return {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}


def _summarize_ocr_payload(raw: dict) -> str:
    """提取 OCR 响应用于日志的摘要（避免打印整段 base64）。"""
    try:
        return json.dumps(raw, ensure_ascii=False)[:2000]
    except TypeError:
        return str(raw)[:2000]


def _extract_qus_payload(raw: dict) -> dict:
    """
    从 only_split=true 同步响应中提取 qus_result 节点。

    常见结构：
    - result.qus_result
    - result.result.qus_result（部分响应带一层嵌套）
    优先选择 qus_result 非空的那一层。
    """
    if not isinstance(raw, dict):
        return {}

    candidates: list[dict] = []
    root = raw.get("result", raw)
    if isinstance(root, dict):
        candidates.append(root)

    cursor: Any = root
    for depth in range(5):
        if not isinstance(cursor, dict):
            break
        nested = cursor.get("result")
        if isinstance(nested, dict):
            candidates.append(nested)
            cursor = nested
        else:
            break

    def _score(node: dict) -> tuple[int, int]:
        qus = node.get("qus_result")
        count = len(qus) if isinstance(qus, list) else 0
        num = node.get("qus_result_num", 0) or 0
        try:
            num = int(num)
        except (TypeError, ValueError):
            num = 0
        return (count, num)

    best = max(candidates, key=_score) if candidates else {}
    logger.debug(
        "OCR 节点解析: 候选 %s 层, 选中 qus_result_len=%s qus_result_num=%s keys=%s",
        len(candidates),
        len(best.get("qus_result") or []),
        best.get("qus_result_num"),
        list(best.keys())[:8],
    )
    return best


def normalize_split_result(raw: dict) -> dict:
    """将百度 OCR 原始切题结果标准化为 Demo 内部结构。"""
    result = _extract_qus_payload(raw)

    qus_result = result.get("qus_result", [])
    if not isinstance(qus_result, list):
        qus_result = []

    logger.info(
        "OCR 原始结果: error_code=%s error_msg=%s qus_result_num=%s qus_result_len=%s enhance_url=%s",
        raw.get("error_code"),
        raw.get("error_msg", ""),
        result.get("qus_result_num"),
        len(qus_result),
        bool(result.get("enhance_url")),
    )
    if not qus_result:
        logger.warning("OCR 未返回任何题目，原始响应摘要: %s", _summarize_ocr_payload(raw))

    questions = []
    for item in qus_result:
        loc = item.get("location", {})
        qus_boxes = _parse_location_items(loc.get("qus_location"))
        pic_boxes = _parse_location_items(loc.get("pic_location"))
        handwrite_boxes = _parse_location_items(loc.get("ans_location"))

        # qus_location 为单题实际区域，作为裁切与多模态输入
        split_box = _union_box(qus_boxes)
        if not split_box and qus_boxes:
            split_box = qus_boxes[0]

        questions.append(
            {
                "qus_id": item.get("qus_id"),
                "big_q_idx": item.get("qus_id"),
                "qus_boxes": qus_boxes,
                "handwrite_boxes": handwrite_boxes,
                "pic_boxes": pic_boxes,
                "split_box": split_box,
            }
        )
        logger.debug(
            "题 %s: qus_boxes=%s handwrite=%s pic=%s split_box=%s",
            item.get("qus_id"),
            len(qus_boxes),
            len(handwrite_boxes),
            len(pic_boxes),
            split_box,
        )

    logger.info("标准化切题结果: %s 道题", len(questions))
    return {
        "total_big_question_count": result.get("qus_result_num", len(questions)) or len(questions),
        "enhance_url": result.get("enhance_url", ""),
        "big_question_list": questions,
        "raw": raw,
    }


def paper_cut_only_split(
    image_bytes: bytes,
    *,
    enhance: bool = False,
    scene_type: str = "paper",
) -> dict:
    """调用 only_split=true 同步切题。"""
    access_token = _get_access_token()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    b64_kb = len(image_b64) / 1024

    logger.info(
        "OCR create_task: image_bytes=%s KB, base64=%.1f KB, enhance=%s, scene_type=%s",
        len(image_bytes) / 1024,
        b64_kb,
        enhance,
        scene_type,
    )
    if b64_kb > 10 * 1024:
        logger.warning("base64 超过 10MB 限制 (%.1f KB)，可能被百度 API 拒绝", b64_kb)

    t0 = time.perf_counter()
    resp = requests.post(
        CREATE_TASK_URL,
        params={"access_token": access_token},
        json={
            "image": image_b64,
            "only_split": True,
            "scene_type": scene_type,
            "enhance": enhance,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info("OCR create_task 响应 HTTP %s, 耗时 %.2fs", resp.status_code, time.perf_counter() - t0)

    if data.get("error_code") not in (None, 0, "0"):
        logger.error(
            "OCR create_task 业务错误: %s",
            _summarize_ocr_payload(data),
        )
        raise RuntimeError(
            f"OCR 切题失败: {data.get('error_code')} {data.get('error_msg')}"
        )

    return normalize_split_result(data)
