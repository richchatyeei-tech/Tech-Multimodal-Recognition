"""图像裁切与坐标变换工具。"""

from __future__ import annotations

import base64
import copy
import io
import logging
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_CROP_PADDING = 8


def load_image(image_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def crop_origin(box: dict[str, float], padding: int = DEFAULT_CROP_PADDING) -> tuple[int, int]:
    """裁切图左上角在原图中的坐标（含 padding）。"""
    return (
        max(0, int(box["x"]) - padding),
        max(0, int(box["y"]) - padding),
    )


def crop_by_box(
    image: Image.Image,
    box: dict[str, float],
    padding: int = DEFAULT_CROP_PADDING,
) -> Image.Image:
    ox, oy = crop_origin(box, padding)
    x2 = min(image.width, int(box["x"] + box["w"]) + padding)
    y2 = min(image.height, int(box["y"] + box["h"]) + padding)
    return image.crop((ox, oy, x2, y2))


def image_to_base64(image: Image.Image, fmt: str = "JPEG") -> str:
    buf = io.BytesIO()
    image.save(buf, format=fmt, quality=92)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def offset_box(box: dict[str, float], ox: float, oy: float) -> dict[str, float]:
    return {
        "x": round(box.get("x", 0) + ox, 2),
        "y": round(box.get("y", 0) + oy, 2),
        "w": round(float(box.get("w", 0)), 2),
        "h": round(float(box.get("h", 0)), 2),
    }


def _offset_box_field(obj: dict[str, Any], key: str, ox: float, oy: float) -> None:
    box = obj.get(key)
    if isinstance(box, dict) and box.get("w", 0) > 0:
        obj[key] = offset_box(box, ox, oy)


def _offset_boxed_list(items: list | None, ox: float, oy: float) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        copy_item = dict(item)
        box = copy_item.get("box")
        if isinstance(box, dict) and box.get("w", 0) > 0:
            copy_item["box"] = offset_box(box, ox, oy)
        result.append(copy_item)
    return result


VLM_COORD_NORM = 1000.0


def _norm_to_crop_box(
    box: dict[str, float], crop_w: int, crop_h: int
) -> dict[str, float]:
    """VLM 0~1000 归一化坐标 → 裁切图像素。"""
    return {
        "x": round(float(box.get("x", 0)) / VLM_COORD_NORM * crop_w, 2),
        "y": round(float(box.get("y", 0)) / VLM_COORD_NORM * crop_h, 2),
        "w": round(float(box.get("w", 0)) / VLM_COORD_NORM * crop_w, 2),
        "h": round(float(box.get("h", 0)) / VLM_COORD_NORM * crop_h, 2),
    }


def _norm_structure_to_crop_pixels(
    structure: dict[str, Any], crop_w: int, crop_h: int
) -> dict[str, Any]:
    result = copy.deepcopy(structure)
    if isinstance(result.get("big_q_title_box"), dict):
        result["big_q_title_box"] = _norm_to_crop_box(
            result["big_q_title_box"], crop_w, crop_h
        )
    for sq in result.get("sub_questions", []):
        if isinstance(sq.get("sub_q_title_box"), dict):
            sq["sub_q_title_box"] = _norm_to_crop_box(
                sq["sub_q_title_box"], crop_w, crop_h
            )
        for key in ("handwrites", "options"):
            for item in sq.get(key, []) or []:
                if isinstance(item.get("box"), dict):
                    item["box"] = _norm_to_crop_box(item["box"], crop_w, crop_h)
    return result


def _clamp_box(box: dict[str, float], image_w: int, image_h: int) -> dict[str, float] | None:
    x = float(box.get("x", 0))
    y = float(box.get("y", 0))
    w = float(box.get("w", 0))
    h = float(box.get("h", 0))
    if w <= 0 or h <= 0:
        return None
    if w > image_w * 0.95 or h > image_h * 0.95:
        return None
    if x + w < 0 or y + h < 0 or x > image_w or y > image_h:
        return None
    return {"x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2)}


def _clamp_structure_boxes(structure: dict[str, Any], image_w: int, image_h: int) -> dict[str, Any]:
    result = copy.deepcopy(structure)
    btb = result.get("big_q_title_box")
    if isinstance(btb, dict):
        clamped = _clamp_box(btb, image_w, image_h)
        if clamped:
            result["big_q_title_box"] = clamped
        else:
            result["big_q_title_box"] = {"x": 0, "y": 0, "w": 0, "h": 0}

    sub_questions = []
    for sq in result.get("sub_questions", []):
        sq_copy = dict(sq)
        stb = sq_copy.get("sub_q_title_box")
        if isinstance(stb, dict):
            clamped = _clamp_box(stb, image_w, image_h)
            if clamped:
                sq_copy["sub_q_title_box"] = clamped
            else:
                sq_copy["sub_q_title_box"] = {"x": 0, "y": 0, "w": 0, "h": 0}
        for key in ("handwrites", "options"):
            cleaned = []
            for item in sq_copy.get(key, []) or []:
                if not isinstance(item, dict):
                    continue
                item_copy = dict(item)
                box = item_copy.get("box")
                if isinstance(box, dict):
                    clamped = _clamp_box(box, image_w, image_h)
                    if clamped:
                        item_copy["box"] = clamped
                        cleaned.append(item_copy)
                else:
                    cleaned.append(item_copy)
            sq_copy[key] = cleaned
        sub_questions.append(sq_copy)
    result["sub_questions"] = sub_questions
    return result


def offset_structure_to_origin(
    structure: dict[str, Any],
    origin_x: float,
    origin_y: float,
    *,
    crop_w: int,
    crop_h: int,
    image_w: int,
    image_h: int,
) -> dict[str, Any]:
    """
    将 VLM 0~1000 归一化坐标映射回原图。

    步骤：归一化 → 裁切图像素 → 加 crop origin。
    origin_x/y 为裁切图左上角在原图中的位置（含 crop padding）。
    """
    logger.debug(
        "VLM 坐标回填原图: origin=(%s,%s) crop=%sx%s norm=0~%s",
        origin_x,
        origin_y,
        crop_w,
        crop_h,
        int(VLM_COORD_NORM),
    )
    crop_pixels = _norm_structure_to_crop_pixels(structure, crop_w, crop_h)
    mapped = dict(crop_pixels)
    _offset_box_field(mapped, "big_q_title_box", origin_x, origin_y)
    sub_questions = []
    for sq in crop_pixels.get("sub_questions", []):
        sq_copy = dict(sq)
        _offset_box_field(sq_copy, "sub_q_title_box", origin_x, origin_y)
        sq_copy["handwrites"] = _offset_boxed_list(sq.get("handwrites"), origin_x, origin_y)
        sq_copy["options"] = _offset_boxed_list(sq.get("options"), origin_x, origin_y)
        sub_questions.append(sq_copy)
    mapped["sub_questions"] = sub_questions

    return _clamp_structure_boxes(mapped, image_w, image_h)
