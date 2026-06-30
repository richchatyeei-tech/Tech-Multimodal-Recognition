# K12 教育文档结构化解析 Demo Spec（CV 粗分 → 多模态结构化）

> 文档版本：v0.3 · 更新日期：2026-06-30  
> 对应工程：教育文档解析方案 demo

---

## 零、Demo 目标与范围

### 0.1 Demo 目标

验证 **「输入试卷图片 → 输出结构化 JSON」** 核心链路的可行性与效果，为教育文档解析产品方案提供技术依据。

**本阶段不做**：AI 批改、对错判定、标准答案生成、分步解析。

### 0.2 MVP 范围

| 类别 | Demo v0（当前） | 后续（P1） |
|------|----------------|-----------|
| 输入 | 单张图片上传（本地文件） | PDF 分页、Url、多图跨页 |
| 粗分切题 | 百度 OCR `only_split=true` 同步切题 | 人工框修正后重跑 |
| 细粒度结构化 | 千帆视觉理解 + Prompt | 自研检测模型、Prompt 迭代 |
| 学科 | 语文、数学典型卷面（VLM 自动识别） | 英语、答题卡等 |
| 交付 | FastAPI 后端 + 可视化 Demo 页 | 同步/异步 API 产品化 |

### 0.3 整体链路

```
图像输入
  → [模块1] CV 粗粒度切题（百度 OCR only_split）
  → 按 qus_location 裁切单题图片
  → [模块2] 多模态结构化解析（千帆 VLM + Prompt）
  → [模块3] 结果汇总组装（坐标回填原图）
  → 结构化 JSON + Demo 可视化
```

### 0.4 工程目录

```
教育文档解析方案demo/
├── backend/
│   ├── main.py                 # FastAPI 入口
│   ├── pipeline.py             # 主流水线
│   ├── config.py               # 环境变量与模型列表
│   ├── clients/
│   │   ├── baidu_ocr.py        # OCR 切题客户端
│   │   └── qianfan_vlm.py      # 千帆视觉理解客户端
│   ├── prompts/
│   │   └── structure.py        # 结构化 Prompt 模板
│   └── utils/
│       └── image_tools.py      # 裁切、坐标变换
├── frontend/
│   └── index.html              # Demo 可视化页面
├── text_sample/                # 测试样例图片
├── scripts/
│   └── verify_apis.py          # 命令行联调脚本
├── .env                        # 密钥（不入库）
└── spec.md                     # 本文档
```

---

## 一、能力资产映射

| 能力 | 来源 | Demo 用法 | 状态 |
|------|------|-----------|------|
| 粗粒度题目切分 | 百度 OCR [试卷切题与识别（多模态）](https://cloud.baidu.com/doc/OCR/s/Cmn8k7ihq) | `only_split=true`，同步返回 `qus_location` + `ans_location` | **已调通** |
| 图像矫正增强 | 同上 API `enhance=true` | 可选开启，获取 `enhance_url` | 已具备，Demo 可开关 |
| 题内细粒度结构化 | 千帆 [视觉理解 API](https://cloud.baidu.com/doc/qianfan-api/s/rm7u7qdiq) | 裁切图 + Prompt → JSON | **已调通**（`ernie-5.0` 已验证） |
| 子题检测/OCR/题型/知识点 | 无成熟原子能力 | 由 VLM Prompt 一并完成 | **验证中**（待样例集评估） |
| Demo 可视化 | `frontend/index.html` | 单题框 + 手写区叠加、Tab 结果、JSON 面板 | **已实现** |

---

## 二、鉴权配置

| 服务 | 环境变量 | 获取方式 | 调用方式 |
|------|----------|----------|----------|
| 百度 OCR 切题 | `BAIDU_OCR_AK` / `BAIDU_OCR_SK` | 智能云 OCR 应用 API Key | OAuth 换 `access_token` |
| 千帆视觉理解 | `QIANFAN_API_KEY` | 控制台 → 安全认证 → API Key | `Authorization: Bearer bce-v3/ALTAK-xxx/xxx` |

> **注意**：OCR 的 AK/SK **不能**直接用于千帆 V2 API，需单独创建千帆 API Key。

配置示例见 `.env.example`。

---

## 三、Demo API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Demo 页面 |
| GET | `/api/models` | 可选 VLM 模型列表 |
| GET | `/api/samples` | `text_sample/` 样例列表 |
| GET | `/api/samples/{filename}` | 获取样例图片 |
| POST | `/api/parse` | **完整流水线**（切题 + 结构化） |
| POST | `/api/split-only` | 仅 OCR 切题 |
| POST | `/api/verify-vlm` | VLM 连通性探测 |
| POST | `/api/verify-structure-prompt` | 单图结构化 Prompt 测试 |

### 3.1 `POST /api/parse` 入参

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| file | 文件 | 必填 | 试卷图片 |
| model | string | `ernie-5.0` | VLM 模型 |
| enable_knowledge_points | bool | false | 是否输出知识点 |
| enhance | bool | false | OCR 矫正增强 |
| skip_vlm | bool | false | true 时仅切题，不调 VLM |
| max_questions | int | 5 | 最多处理题数（Demo 限流） |

### 3.2 候选 VLM 模型

| 模型 ID | 展示名 | 厂商 | 凭证 |
|---------|--------|------|------|
| `ernie-5.0` | ERNIE 5.0（千帆） | 千帆 | `QIANFAN_API_KEY` |
| `qwen3-vl-235b-a22b-instruct` | Qwen3-VL 235B（千帆） | 千帆 | `QIANFAN_API_KEY` |
| `doubao-seed-2-1-pro-260628` | 豆包 2.1 Pro（华严） | 华严 OpenAI 兼容 | `HUAYAN_API_KEY` |
| `gemini-3.1-pro-preview` | Gemini 3.1 Pro Preview（华严） | 华严 OpenAI 兼容 | `HUAYAN_API_KEY` |

模型列表由 `backend/config.py` 的 `VLM_MODEL_SPECS` 配置；`backend/clients/vlm_client.py` 按 `provider` 路由到千帆或华严客户端。

---

## 四、全局输入输出约束

### 4.1 上游输入（模块 1 / OCR）

| 参数 | 说明 |
|------|------|
| image | Base64，≤10M；支持 jpg/jpeg/png/bmp |
| only_split | 固定 `true`（同步切题） |
| scene_type | 固定 `paper` |
| enhance | 可选 `true` |

### 4.2 全局控制配置 `ParseConfigMap`

对应 Demo 页面开关与 `/api/parse` 入参：

```json
{
  "EnableKnowledgePoints": false,
  "EnhanceImage": false,
  "VlmModel": "ernie-5.0",
  "SkipVlm": false,
  "MaxQuestions": 5
}
```

### 4.3 全局输出结构

顶层 `JobStatus`：`DONE` / `FAILED` / `PARTIAL`

核心数组 `QuestionInfos[]`：一级元素 = OCR 切出的单题（`qus_id`）；`SubQuestions[]` = VLM 结构化子题；元素坐标均在**原图**坐标系。

---

## 五、模块 1：CV 粗粒度切题（百度 OCR）

### 5.1 接口说明

- **接口**：`POST https://aip.baidubce.com/rest/2.0/ocr/v1/paper_cut_edu_vlm/create_task`
- **模式**：`only_split=true` → **同步返回**（无需轮询）
- **实现**：`backend/clients/baidu_ocr.py`

### 5.2 坐标字段语义（重要）

百度返回 `qus_result[]`，每题 `location` 含三类框：

| 百度字段 | 语义 | 内部映射 | 用途 |
|----------|------|----------|------|
| `qus_location` | **单题实际区域** | `qus_boxes[]` → `split_box` | **裁切图、多模态输入、可视化蓝框** |
| `ans_location` | OCR 手写作答区域 | `handwrite_boxes[]` → `OcrHandwriteBoxes` | 仅 JSON 保留，**不用于可视化** |
| `pic_location` | 题目内配图区域 | `pic_boxes[]` → `PicBoxes` | **可视化橙框（figure）** |

**坐标格式转换**：

- 百度原始：官方 `{x, y, w, h}` 或旧版 `coordinate: [x1, y1, x2, y2]`
- 内部统一：`{x, y, w, h}`，其中 `w = x2 - x1`，`h = y2 - y1`
- 参照系：原图（或 `enhance_url` 矫正图，若 `enhance=true`）

**裁切规则**：

```
split_box = union(qus_location 全部框)
若仅一个框 → 直接使用该框
```

### 5.3 模块输出结构体

```json
{
  "total_big_question_count": 9,
  "enhance_url": "",
  "big_question_list": [
    {
      "qus_id": 1,
      "big_q_idx": 1,
      "qus_boxes": [{ "x": 136.94, "y": 113.29, "w": 390.93, "h": 55.57, "score": 0.77 }],
      "split_box": { "x": 136.94, "y": 113.29, "w": 390.93, "h": 55.57 },
      "handwrite_boxes": [{ "x": 375.43, "y": 116.4, "w": 146.52, "h": 50.19 }],
      "pic_boxes": [],
      "crop_sub_img_base64": "xxx"
    }
  ]
}
```

### 5.4 约束与异常

| 场景 | 处理 |
|------|------|
| 无任何题目 | `JobStatus=FAILED`，`ErrorCode=NO_QUESTION_DETECTED` |
| 单页题目过多 | Demo 通过 `max_questions` 截断 |
| 百度 API 错误 | 透传 `error_code` / `error_msg` |

---

## 六、模块 2：多模态结构化解析（千帆 VLM）

### 6.1 接口说明

- **接口**：`POST https://qianfan.baidubce.com/v2/chat/completions`
- **鉴权**：`Authorization: Bearer {QIANFAN_API_KEY}`
- **实现**：`backend/clients/qianfan_vlm.py`
- **Prompt**：`backend/prompts/structure.py`

### 6.2 模块输入

| 输入 | 说明 |
|------|------|
| 裁切图 | 按 `split_box`（`qus_location`）从原图裁切 |
| `split_box` | 原图坐标，用于 VLM 子字段坐标回填 |
| `pic_boxes` | OCR `pic_location`，配图框，不经 VLM |
| `ParseConfigMap` | 模型选择、知识点开关等 |

### 6.3 核心能力

针对**单题裁切图**，由 VLM 完成：

1. **层级拆解**：大题标题 → 子小题 `(1)(2)(3)`
2. **区域框 + 文本**：主题干框、子题干框、手写作答（`handwrites`）、选项（`options`）
3. **语义提取**（可选）：学科、题型、知识点

**不由 VLM 负责**：配图/图表框 → 使用 OCR `pic_location`（`PicBoxes`）

### 6.4 Prompt 要点

- 输出**纯 JSON**，不含 markdown 代码块
- **Prompt 只描述输入图片**：VLM 仅看到单题裁切图，不涉及整卷原图
- 坐标**固定为输入图 0~1000 归一化**（原点=左上角，1000=右/下边缘）：
  - `x`、`w` 相对图片宽度；`y`、`h` 相对图片高度
  - `0 ≤ x,y,w,h ≤ 1000`，且 `x+w ≤ 1000`，`y+h ≤ 1000`
- **后端**（非 Prompt）两步回填整卷原图：

```
crop_x = VLM_x / 1000 × crop_width
原图_x = crop_origin_x + crop_x
```

- 超大异常框（宽/高 > 原图 95%）在输出前过滤

- `EnableKnowledgePoints=false` 时，`knowledge_points` 输出空数组

**公式 LaTeX 约定**（内联在文本字段中，不设独立 `has_formula` 字段）：

| 规则 | 说明 |
|------|------|
| 适用字段 | `big_q_title`、`sub_q_title`、`options[].text`、`handwrites[].text` |
| 行内公式 | `$...$` 包裹，与普通文字混排 |
| 独立行公式 | 可选 `$$...$$` |
| 常用命令 | `\frac{}{}`、`\sqrt{}`、上下标 `^` `_` 等 |
| JSON 转义 | LaTeX 反斜杠在 JSON 中双写，如 `\\frac` |
| 看不清 | 不猜测，对应 `text` 留空字符串 |

### 6.5 模块输出结构体（单题 VLM JSON）

> 不使用 `elements` 数组；子题层用 `handwrites` / `options` 显式字段，语义更清晰。

```json
{
  "big_q_title": "(一) 根据语境拼写词语。(10分)",
  "big_q_title_box": { "x": 10, "y": 5, "w": 280, "h": 24 },
  "subject": "chinese",
  "question_type": "看拼音写词语",
  "knowledge_points": [],
  "sub_questions": [
    {
      "sub_q_idx": 1,
      "sub_q_title": "(1)我zhǔn bèi()安心shuì jiào()...",
      "sub_q_title_box": { "x": 8, "y": 30, "w": 260, "h": 40 },
      "handwrites": [
        { "text": "准备", "box": { "x": 120, "y": 200, "w": 180, "h": 60 } }
      ],
      "options": [
        { "label": "A", "text": "选项内容", "box": { "x": 0, "y": 0, "w": 0, "h": 0 } }
      ]
    }
  ]
}
```

数学卷示例（公式内联 LaTeX）：

```json
{
  "sub_q_title": "(1) 解方程 $\\frac{1}{2}x + 3 = 7$，求 $x$",
  "handwrites": [{ "text": "$x = 8$", "box": { "x": 120, "y": 200, "w": 80, "h": 40 } }]
}
```

> 注：`big_q_title_box`、`sub_q_title_box`、`handwrites[].box`、`options[].box` 在流水线输出前已映射为原图坐标。

### 6.6 约束

| 场景 | 处理 |
|------|------|
| 单题 VLM 失败 | `ParseStatus=FAILED`，其余题继续 → `JobStatus=PARTIAL` |
| 子题部分失败 | 保留已成功子题（待 Prompt 细化） |
| 并发 | Demo 大题级并行，线程池 `max_workers=2` |

---

## 七、模块 3：结果汇总组装

### 7.1 能力

1. 合并 OCR 切题框 + VLM 结构化内容
2. 坐标回填至原图
3. 统计：切题数、结构化成功/失败数、子题总数
4. 封装统一 `Response` 供前端消费

### 7.2 最终对外输出（Demo Response）

```json
{
  "RequestId": "uuid-xxx",
  "Response": {
    "JobStatus": "DONE",
    "ErrorCode": "",
    "ErrorMessage": "",
    "ImageWidth": 1280,
    "ImageHeight": 1706,
    "EnhanceUrl": "",
    "Stats": {
      "total_big_questions": 5,
      "parsed_big_questions": 4,
      "failed_big_questions": 1,
      "total_sub_questions": 12
    },
    "QuestionInfos": [
      {
        "BigQIdx": 1,
        "QusId": 1,
        "ParseStatus": "SUCCESS",
        "SplitBox": { "x": 136.94, "y": 113.29, "w": 390.93, "h": 55.57 },
        "QusBoxes": [{ "x": 136.94, "y": 113.29, "w": 390.93, "h": 55.57 }],
        "PicBoxes": [{ "x": 200, "y": 150, "w": 80, "h": 60 }],
        "OcrHandwriteBoxes": [{ "x": 375.43, "y": 116.4, "w": 146.52, "h": 50.19 }],
        "CropBase64": "xxx",
        "BigQTitle": "(一) 根据语境拼写词语。(10分)",
        "BigQTitleBox": { "x": 140, "y": 115, "w": 200, "h": 22 },
        "Subject": "chinese",
        "QuestionType": "看拼音写词语",
        "KnowledgePoints": [],
        "SubQuestions": [
          {
            "sub_q_idx": 1,
            "sub_q_title": "(1)我zhǔn bèi()...",
            "sub_q_title_box": { "x": 142, "y": 140, "w": 300, "h": 35 },
            "handwrites": [
              { "text": "准备", "box": { "x": 260, "y": 313, "w": 180, "h": 60 } }
            ],
            "options": []
          }
        ],
        "Error": null
      }
    ]
  }
}
```

---

## 八、异常流程

| 场景 | ErrorCode | JobStatus |
|------|-----------|-----------|
| 图片格式/大小不合规 | INVALID_IMAGE | FAILED |
| CV 未检测到题目 | NO_QUESTION_DETECTED | FAILED |
| 单题结构化失败 | — | PARTIAL（该题 `ParseStatus=FAILED`） |
| VLM 服务不可用 | — | FAILED 或 PARTIAL |

---

## 九、Demo 性能与验收（观测指标）

| 指标 | Demo 目标 | 当前观测 |
|------|-----------|----------|
| OCR 切题 | ≤ 3s | 样例卷 ~2s，检出 9 题 |
| 单题 VLM 结构化 | ≤ 15s | `ernie-5.0` ~20s（整图探测） |
| 端到端（5 题） | P95 ≤ 60s | 待批量测试 |
| 切题框准确性 | `qus_location` IoU ≥ 0.8 | 待人工标注评估 |
| 结构化准确率 | 题干+手写可读正确率 ≥ 85% | 待 3 张样例抽检 |

---

## 十、Demo 前端页面

### 10.1 布局

```
┌──────────────────────────────────────────────────────────────┐
│  教育文档结构化解析 Demo    [样例▼] [上传] [模型▼] [开关] [解析] │
├───────────────────────┬──────────────────────────────────────┤
│  原图 Canvas 叠加      │  统计栏 + Tab(题1|题2|...)            │
│  · 蓝 = qus_location   │  子题 handwrites / options 列表       │
│  · 橙 = pic_location   │  完整 JSON（可折叠）                    │
│  · 紫/蓝/绿 = VLM框    │                                      │
└───────────────────────┴──────────────────────────────────────┘
```

### 10.2 已实现交互

1. 样例下拉 / 本地图片上传
2. 模型选择、`仅切题`、`矫正增强`、`知识点` 开关
3. Canvas 分层绘制：`SplitBox`（蓝·OCR）、`PicBoxes`（橙·OCR）、VLM `BigQTitleBox` / `sub_q_title_box` / `options` / `handwrites`
4. 结构化结果分 Tab 展示 handwrites/options，底部 JSON 面板
5. 「测试 VLM」独立连通性按钮

### 10.3 技术栈

- 前端：单页 `index.html` + 原生 JS + Canvas
- 后端：Python FastAPI + Pillow
- 启动：`uvicorn backend.main:app --port 8080`

---

## 十一、联调记录

| 项目 | 结论 | 日期 |
|------|------|------|
| OCR `only_split=true` | 调通；坐标 `{x,y,w,h}`；`qus_location` 裁切 | 2026-06-30 |
| 可视化框来源拆分 | 配图→`pic_location`；手写→VLM `handwrites` | 2026-06-30 |
| Prompt Schema | 弃用 `elements`，改用 `handwrites`/`options` | 2026-06-30 |
| 千帆 `ernie-5.0` | 调通 | 2026-06-30 |
| 千帆 `qwen3-vl-235b-a22b-instruct` | 待对比测试 | — |
| 华严 `doubao-seed-2-1-pro-260628` | 已接入路由，待联调 | 2026-06-30 |
| 华严 `gemini-3.1-pro-preview` | 已接入路由，待联调 | 2026-06-30 |
| 结构化 Prompt 全链路 | 待样例批量验证 | — |

### 快速验证命令

```bash
pip install -r requirements.txt
python scripts/verify_apis.py              # OCR + VLM
python scripts/verify_apis.py --skip-vlm   # 仅 OCR
python scripts/verify_structure_schema.py  # Schema/坐标回填（离线）
uvicorn backend.main:app --port 8080
```

样例目录：`text_sample/`（3 张jpg）

---

## 十二、后续规划（P1）

- [ ] `ernie-5.0` vs `qwen3-vl-235b-a22b-instruct` 结构化效果对比报告
- [ ] 验收测试集人工标注（10 张卷）与指标统计
- [ ] Prompt 迭代：子题切分稳定性、坐标精度、内联 LaTeX 公式识别质量
- [ ] 前端 KaTeX/MathJax 渲染内联 LaTeX
- [ ] 切题框手动修正 → 重跑结构化
- [ ] PDF / 多页输入支持
- [ ] 批改模块（独立 Spec，不在本 Demo 范围）
