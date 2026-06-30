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
    assert "输入图片" in prompt
    assert "0~1000" in prompt
    assert "像素" not in prompt or "不要输出像素" in prompt
    assert "原图" not in prompt
    print("  [OK] Prompt 含 handwrites/options 与 0~1000 坐标约定")


def test_norm_to_origin() -> None:
    """0~1000 归一化 → 裁切像素 → 加 origin 回填原图。"""
    split_box = {"x": 100, "y": 200, "w": 300, "h": 400}
    origin_x, origin_y = crop_origin(split_box)
    assert origin_x == 92 and origin_y == 192
    crop_w, crop_h = 316, 416

    structure = {
        "big_q_title_box": {"x": 100, "y": 100, "w": 500, "h": 100},
        "sub_questions": [
            {
                "sub_q_idx": 1,
                "handwrites": [{"text": "答案", "box": {"x": 200, "y": 300, "w": 150, "h": 50}}],
                "options": [],
            }
        ],
    }
    mapped = offset_structure_to_origin(
        structure,
        origin_x,
        origin_y,
        crop_w=crop_w,
        crop_h=crop_h,
        image_w=2000,
        image_h=3000,
    )
    # big_q: x=100/1000*316+92=123.6, handwrite x=200/1000*316+92=155.2
    assert mapped["big_q_title_box"]["x"] == 123.6
    assert mapped["sub_questions"][0]["handwrites"][0]["box"]["x"] == 155.2
    print("  [OK] 0~1000 归一化坐标回填原图")


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
    test_norm_to_origin()
    test_pic_location_parse()
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
