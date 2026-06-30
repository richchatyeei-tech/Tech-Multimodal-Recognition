# 教育文档结构化解析 Demo

K12 试卷图片的结构化解析验证项目：**整卷原图 → 百度 OCR 粗切题 → 多模态 VLM 细粒度结构化 → 原图坐标 JSON + Canvas 可视化**。

详细设计见 [spec.md](./spec.md)。

## 流水线

```
原图
  → OCR only_split（qus_location → split_box）
  → 按 split_box 裁切单题图（含 8px padding）
  → VLM 结构化（子题干 / 手写 / 选项 / 学科题型）
  → 0~1000 归一化坐标 → 裁切像素 → 回填原图
  → 前端在原图上叠加绘制
```

## 快速开始

```bash
cd 教育文档解析方案demo
pip install -r requirements.txt
cp .env.example .env   # 填入密钥
python scripts/verify_apis.py --skip-vlm      # 验证 OCR
python scripts/verify_structure_schema.py     # 离线验证坐标 Schema
uvicorn backend.main:app --reload --port 8080
```

浏览器打开 http://127.0.0.1:8080 ，上传图片或选择 `text_sample/` 样例后点击解析。

## 鉴权配置

| 能力 | 环境变量 | 说明 |
|------|----------|------|
| OCR 试卷切题 | `BAIDU_OCR_AK` / `BAIDU_OCR_SK` | 百度智能云 OCR 应用 API Key |
| 千帆视觉理解 | `QIANFAN_API_KEY` | 格式 `bce-v3/ALTAK-xxx/xxx`，与 OCR AK/SK **不同** |
| 华严网关（豆包/Gemini 等） | `HUAYAN_API_KEY` | OpenAI 兼容接口，`sk-` 开头 |

## 支持的 VLM 模型

| 模型 ID | 展示名 | 厂商 |
|---------|--------|------|
| `ernie-5.0` | ERNIE 5.0（千帆） | 千帆 |
| `qwen3-vl-235b-a22b-instruct` | Qwen3-VL 235B（千帆） | 千帆 |
| `doubao-seed-2-1-pro-260628` | 豆包 2.1 Pro（华严） | 华严 |
| `gemini-3.1-pro-preview` | Gemini 3.1 Pro Preview（华严） | 华严 |

前端下拉框切换模型；千帆与华严由 `backend/clients/vlm_client.py` 统一路由。

## 坐标约定

VLM **只看到单题裁切图**，Prompt 要求输出 **0~1000 归一化坐标**（相对输入图宽/高，原点=左上角）。

后端固定两步变换（`backend/utils/image_tools.py`）：

```
crop_x = VLM_x / 1000 × crop_width
原图_x = crop_origin_x + crop_x
```

对外 JSON 中所有框均在**整卷原图**坐标系。配图框来自 OCR `pic_location`，不经 VLM。

公式以 **LaTeX 内联**在 `sub_q_title`、`handwrites[].text` 等文本字段中（如 `$x=8$`），不设独立公式字段。

## 可视化图例

| 颜色 | 来源 | 含义 |
|------|------|------|
| 蓝 | OCR | 单题切题框 `SplitBox` |
| 橙 | OCR | 配图 `PicBoxes` |
| 黄 | VLM | 大题标题 `BigQTitleBox` |
| 紫 | VLM | 子题干 `sub_q_title_box` |
| 青 | VLM | 选项 `options[].box` |
| 绿 | VLM | 手写作答 `handwrites[].box` |

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/parse` | 完整流水线（OCR + VLM） |
| `POST` | `/api/split-only` | 仅 OCR 切题 |
| `POST` | `/api/verify-vlm` | VLM 连通性测试 |
| `GET` | `/api/models` | 可选模型列表 |
| `GET` | `/api/samples` | 样例图片列表 |

## 验证脚本

```bash
python scripts/verify_apis.py              # OCR + VLM 联调
python scripts/verify_apis.py --skip-vlm   # 仅 OCR
python scripts/verify_structure_schema.py  # Schema / 坐标回填（离线）

# 诊断单题 VLM 坐标参照系（需网络）
python scripts/diagnose_coords.py path/to/image.jpg --question 3 --model doubao-seed-2-1-pro-260628
```

## 项目结构

```
backend/
  main.py              # FastAPI 入口
  pipeline.py          # OCR → VLM → 组装主流水线
  prompts/structure.py # 结构化 Prompt
  clients/
    baidu_ocr.py       # 百度试卷切题
    qianfan_vlm.py     # 千帆多模态
    huayan_vlm.py      # 华严网关（豆包/Gemini）
    vlm_client.py      # VLM 统一路由
  utils/image_tools.py # 裁切、0~1000 坐标变换
frontend/index.html    # 上传 + Canvas 可视化
text_sample/           # 样例图片
spec.md                # 完整技术规格
```

## 样例图片

放在 `text_sample/` 目录，前端「选择样例」下拉框自动加载。
