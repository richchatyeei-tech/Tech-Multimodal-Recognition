#!/usr/bin/env python3
"""验证百度 OCR 切题与千帆 VLM 连通性。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.clients.baidu_ocr import paper_cut_only_split
from backend.clients.vlm_client import chat_vision
from backend.config import QIANFAN_API_KEY, HUAYAN_API_KEY, get_model_spec, SAMPLE_DIR


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, help="测试图片路径")
    parser.add_argument("--model", default="ernie-5.0")
    parser.add_argument("--skip-vlm", action="store_true")
    args = parser.parse_args()

    image_path = args.image
    if not image_path:
        samples = list(SAMPLE_DIR.glob("*.jpg")) + list(SAMPLE_DIR.glob("*.png"))
        if not samples:
            print("未找到样例图片")
            return 1
        image_path = samples[0]

    image_bytes = image_path.read_bytes()
    print(f"图片: {image_path} ({len(image_bytes)} bytes)")

    print("\n[1/2] OCR only_split …")
    split = paper_cut_only_split(image_bytes)
    print(f"  切题数量: {split['total_big_question_count']}")
    for q in split["big_question_list"][:3]:
        print(f"  题{q['qus_id']}: split_box={q.get('split_box')}")

    if args.skip_vlm:
        print("\n跳过 VLM 测试")
        return 0

    try:
        spec = get_model_spec(args.model)
    except ValueError as exc:
        print(f"\n[2/2] VLM 失败: {exc}")
        return 1

    if spec["provider"] == "qianfan" and not QIANFAN_API_KEY:
        print(
            "\n[2/2] VLM 跳过：未配置 QIANFAN_API_KEY\n"
            "  请在 .env 填入千帆控制台 API Key（bce-v3/ALTAK-.../...）"
        )
        return 0

    if spec["provider"] == "huayan" and not HUAYAN_API_KEY:
        print(
            "\n[2/2] VLM 跳过：未配置 HUAYAN_API_KEY\n"
            "  请在 .env 填入华严 API Key（sk-...）"
        )
        return 0

    print(f"\n[2/2] VLM 连通性测试 model={args.model} provider={spec['provider']} …")
    try:
        text = chat_vision(
            model=args.model,
            prompt="请用一句话描述这张试卷图片。",
            image_bytes=image_bytes,
        )
        print(f"  OK: {text[:200]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
