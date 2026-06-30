# 教育文档结构化解析 Demo

验证链路：**图片 → 百度 OCR 粗切题 → 千帆多模态结构化 → JSON + 可视化**

## 快速开始

```bash
cd 教育文档解析方案demo
pip install -r requirements.txt
cp .env.example .env   # 编辑填入密钥
python scripts/verify_apis.py --skip-vlm   # 先验证 OCR
uvicorn backend.main:app --reload --port 8080
```

浏览器打开 http://127.0.0.1:8080

## 鉴权说明（重要）

| 能力 | 凭证 | 获取方式 |
|------|------|----------|
| OCR 试卷切题 | `BAIDU_OCR_AK` / `BAIDU_OCR_SK` | 百度智能云 OCR 应用 API Key |
| 千帆视觉理解 | `QIANFAN_API_KEY` | 控制台 → 安全认证 → API Key，格式 `bce-v3/ALTAK-xxx/xxx` |

**OCR 的 AK/SK 不能直接用于千帆 V2 API**，需单独创建千帆 API Key。

## 样例图片

放在 `text_sample/` 目录。

## API

- `POST /api/parse` — 完整流水线
- `POST /api/split-only` — 仅 OCR 切题
- `POST /api/verify-vlm` — VLM 连通性测试

## 候选模型

- `ernie-5.0`
- `qwen3-vl-235b-a22b-instruct`
