#!/usr/bin/env python3
"""诊断 VLM 坐标参照系：对比裁切图 / 原图 / split_box 范围。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.clients.baidu_ocr import paper_cut_only_split
from backend.clients.vlm_client import chat_vision, extract_json_from_text
from backend.prompts.structure import build_structure_prompt
from backend.utils.image_tools import crop_by_box, crop_origin, load_image


def _iter_boxes(structure: dict):
    if isinstance(structure.get("big_q_title_box"), dict):
        b = structure["big_q_title_box"]
        if b.get("w", 0) > 0:
            yield "big_q_title_box", b
    for sq in structure.get("sub_questions", []) or []:
        if not isinstance(sq, dict):
            continue
        idx = sq.get("sub_q_idx", "?")
        if isinstance(sq.get("sub_q_title_box"), dict):
            b = sq["sub_q_title_box"]
            if b.get("w", 0) > 0:
                yield f"sub_q{idx}_title", b
        for hw_i, hw in enumerate(sq.get("handwrites") or []):
            if isinstance(hw.get("box"), dict) and hw["box"].get("w", 0) > 0:
                yield f"sub_q{idx}_hw{hw_i}", hw["box"]
        for opt in sq.get("options") or []:
            if isinstance(opt.get("box"), dict) and opt["box"].get("w", 0) > 0:
                yield f"sub_q{idx}_opt_{opt.get('label','')}", opt["box"]


def _extent(boxes):
    if not boxes:
        return 0, 0
    return (
        max(b["x"] + b["w"] for _, b in boxes),
        max(b["y"] + b["h"] for _, b in boxes),
    )


def _in_crop(box, cw, ch):
    return (
        box["x"] >= 0
        and box["y"] >= 0
        and box["x"] + box["w"] <= cw + 1
        and box["y"] + box["h"] <= ch + 1
    )


def _in_split(box, sb):
    return (
        box["x"] >= sb["x"] - 2
        and box["y"] >= sb["y"] - 2
        and box["x"] + box["w"] <= sb["x"] + sb["w"] + 2
        and box["y"] + box["h"] <= sb["y"] + sb["h"] + 2
    )


def diagnose_question(image_path: Path, big_q_idx: int, model: str) -> None:
    image_bytes = image_path.read_bytes()
    image = load_image(image_bytes)
    split = paper_cut_only_split(image_bytes)
    q = split["big_question_list"][big_q_idx - 1]
    split_box = q["split_box"]
    crop = crop_by_box(image, split_box)
    ox, oy = crop_origin(split_box)

    from io import BytesIO

    buf = BytesIO()
    crop.save(buf, format="JPEG", quality=92)
    crop_bytes = buf.getvalue()

    prompt = build_structure_prompt(crop_width=crop.width, crop_height=crop.height)
    raw = chat_vision(model=model, prompt=prompt, image_bytes=crop_bytes)
    structure = extract_json_from_text(raw)
    boxes = list(_iter_boxes(structure))
    max_x, max_y = _extent(boxes)

    print(f"\n=== 题 {big_q_idx} | model={model} ===")
    print(f"原图: {image.width}x{image.height}")
    print(f"split_box: {json.dumps(split_box)}")
    print(f"crop: {crop.width}x{crop.height}  origin=({ox},{oy})")
    print(f"VLM box 数量: {len(boxes)}  max_extent=({max_x:.1f},{max_y:.1f})")

    in_crop = sum(1 for _, b in boxes if _in_crop(b, crop.width, crop.height))
    in_split = sum(1 for _, b in boxes if _in_split(b, split_box))
    print(f"落在 crop 内: {in_crop}/{len(boxes)}  落在 split_box 内(原图): {in_split}/{len(boxes)}")

    if max_x <= 1000.5 and max_y <= 1000.5:
        print("✓ 坐标在 0~1000 归一化范围内（符合方案 A）")
    if max_x > crop.width or max_y > crop.height:
        print("⚠ 超出裁切图尺寸 → 非裁切图像素坐标")
    if in_split > in_crop and in_split >= len(boxes) * 0.5:
        print("⚠ 多数框落在 split_box 原图范围 → 疑似整页绝对坐标")

    for name, b in boxes:
        flags = []
        if not _in_crop(b, crop.width, crop.height):
            flags.append("超crop")
        if not _in_split(b, split_box):
            flags.append("超split")
        flag = " ".join(flags) if flags else "ok"
        print(f"  {name}: x={b['x']:.0f} y={b['y']:.0f} w={b['w']:.0f} h={b['h']:.0f}  [{flag}]")


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("image", type=Path)
    p.add_argument("--model", default="doubao-seed-2-1-pro-260628")
    p.add_argument("--question", type=int, default=3)
    args = p.parse_args()

    diagnose_question(args.image, args.question, args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
