#!/usr/bin/env python3
"""验证结构化 Schema、坐标回填与 OCR pic_location 解析（无需网络）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.clients.baidu_ocr import normalize_split_result
from backend.prompts.structure import build_structure_prompt
from backend.utils.image_tools import crop_origin, offset_structure_to_origin


def test_prompt_schema() -> None:
    prompt = build_structure_prompt(crop_width=800, crop_height=1200)
    assert "handwrites" in prompt
    assert "options" in prompt
    assert "LaTeX" in prompt
    assert "has_formula" not in prompt
    assert "elements" not in prompt
    assert "800" in prompt and "1200" in prompt
    assert "输入图片" in prompt and "像素" in prompt
    assert "原图" not in prompt
    assert "0~1000" in prompt  # 禁止项说明
    print("  [OK] Prompt 含 handwrites/options 与输入图像素坐标约定")


def test_offset_uses_crop_origin() -> None:
    split_box = {"x": 100, "y": 200, "w": 300, "h": 400}
    origin_x, origin_y = crop_origin(split_box)
    assert origin_x == 92 and origin_y == 192

    structure = {
        "big_q_title_box": {"x": 10, "y": 20, "w": 100, "h": 30},
        "sub_questions": [
            {
                "sub_q_idx": 1,
                "handwrites": [{"text": "答案", "box": {"x": 30, "y": 70, "w": 40, "h": 15}}],
                "options": [],
            }
        ],
    }
    mapped = offset_structure_to_origin(
        structure,
        origin_x,
        origin_y,
        crop_w=316,
        crop_h=416,
        image_w=2000,
        image_h=3000,
    )
    assert mapped["big_q_title_box"]["x"] == 102
    assert mapped["sub_questions"][0]["handwrites"][0]["box"]["x"] == 122
    print("  [OK] 坐标按裁切图 origin（含 padding）回填")


def test_always_offset_crop_pixel_coords() -> None:
    """无论坐标大小，一律按裁切图像素 + origin 回填（不做原图绝对坐标猜测）。"""
    structure = {
        "big_q_title_box": {"x": 120, "y": 80, "w": 100, "h": 30},
        "sub_questions": [],
    }
    mapped = offset_structure_to_origin(
        structure,
        92,
        192,
        crop_w=300,
        crop_h=400,
        image_w=2000,
        image_h=3000,
    )
    assert mapped["big_q_title_box"]["x"] == 212
    assert mapped["big_q_title_box"]["y"] == 272
    print("  [OK] 裁切图像素坐标无条件回填原图")


def test_pic_location_parse() -> None:
    raw = {
        "error_code": "0",
        "result": {
            "qus_result_num": 1,
            "qus_result": [
                {
                    "qus_id": 1,
                    "location": {
                        "qus_location": [{"x": 10, "y": 20, "w": 300, "h": 400}],
                        "pic_location": [{"x": 50, "y": 60, "w": 120, "h": 80}],
                        "ans_location": [],
                    },
                }
            ],
        },
    }
    split = normalize_split_result(raw)
    q = split["big_question_list"][0]
    assert len(q["pic_boxes"]) == 1
    assert q["pic_boxes"][0]["w"] == 120
    print("  [OK] OCR pic_location → pic_boxes")


def main() -> int:
    print("验证结构化 Schema …")
    test_prompt_schema()
    test_offset_uses_crop_origin()
    test_always_offset_crop_pixel_coords()
    test_pic_location_parse()
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
