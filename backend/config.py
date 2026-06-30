"""配置加载。"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

BAIDU_OCR_AK = os.getenv("BAIDU_OCR_AK", "")
BAIDU_OCR_SK = os.getenv("BAIDU_OCR_SK", "")
QIANFAN_API_KEY = os.getenv("QIANFAN_API_KEY", "")
HUAYAN_API_KEY = os.getenv("HUAYAN_API_KEY", "")
HUAYAN_API_BASE = os.getenv(
    "HUAYAN_API_BASE", "https://www.huayanapi.com/v1"
)

SAMPLE_DIR = ROOT_DIR / "text_sample"
FRONTEND_DIR = ROOT_DIR / "frontend"

# id: API 模型名；label: 前端展示名；provider: qianfan | huayan
VLM_MODEL_SPECS: list[dict[str, str]] = [
    {"id": "ernie-5.0", "label": "ERNIE 5.0（千帆）", "provider": "qianfan"},
    {
        "id": "qwen3-vl-235b-a22b-instruct",
        "label": "Qwen3-VL 235B（千帆）",
        "provider": "qianfan",
    },
    {
        "id": "doubao-seed-2-1-pro-260628",
        "label": "豆包 2.1 Pro（华严）",
        "provider": "huayan",
    },
    {
        "id": "gemini-3.1-pro-preview",
        "label": "Gemini 3.1 Pro Preview（华严）",
        "provider": "huayan",
    },
]

VLM_MODELS = [m["id"] for m in VLM_MODEL_SPECS]


def get_model_spec(model_id: str) -> dict[str, str]:
    for spec in VLM_MODEL_SPECS:
        if spec["id"] == model_id:
            return spec
    raise ValueError(f"未知 VLM 模型: {model_id}")
