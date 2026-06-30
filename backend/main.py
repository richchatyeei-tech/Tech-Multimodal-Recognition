"""FastAPI Demo 服务。"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.clients.baidu_ocr import paper_cut_only_split
from backend.clients.vlm_client import chat_vision
from backend.config import FRONTEND_DIR, SAMPLE_DIR, VLM_MODEL_SPECS
from backend.log_config import setup_logging
from backend.pipeline import run_pipeline
from backend.prompts.structure import build_structure_prompt

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="教育文档结构化解析 Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def index():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(404, "frontend/index.html 不存在")
    return FileResponse(index_file)


@app.get("/api/models")
async def list_models():
    return {"models": VLM_MODEL_SPECS}


@app.get("/api/samples")
async def list_samples():
    if not SAMPLE_DIR.exists():
        return {"samples": []}
    files = sorted(
        f.name for f in SAMPLE_DIR.iterdir() if f.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    return {"samples": files}


@app.get("/api/samples/{filename}")
async def get_sample(filename: str):
    path = SAMPLE_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(404, "样例不存在")
    return FileResponse(path)


@app.post("/api/parse")
async def parse_document(
    file: UploadFile = File(...),
    model: str = Form("ernie-5.0"),
    enable_knowledge_points: bool = Form(False),
    enhance: bool = Form(False),
    skip_vlm: bool = Form(False),
    max_questions: int = Form(5),
):
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(400, "空文件")

    logger.info(
        "POST /api/parse file=%s size=%.1fKB model=%s enhance=%s skip_vlm=%s max_questions=%s",
        file.filename,
        len(image_bytes) / 1024,
        model,
        enhance,
        skip_vlm,
        max_questions,
    )

    try:
        result = run_pipeline(
            image_bytes,
            model=model,
            enable_knowledge_points=enable_knowledge_points,
            enhance=enhance,
            skip_vlm=skip_vlm,
            max_questions=max_questions,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("POST /api/parse 失败: %s", exc)
        raise HTTPException(500, str(exc)) from exc

    resp = result.get("Response", {})
    logger.info(
        "POST /api/parse 完成 request_id=%s status=%s questions=%s",
        result.get("RequestId"),
        resp.get("JobStatus"),
        resp.get("Stats", {}).get("total_big_questions"),
    )
    return result


@app.post("/api/split-only")
async def split_only(file: UploadFile = File(...), enhance: bool = Form(False)):
    """仅 OCR 切题，用于快速验证。"""
    image_bytes = await file.read()
    logger.info(
        "POST /api/split-only file=%s size=%.1fKB enhance=%s",
        file.filename,
        len(image_bytes) / 1024,
        enhance,
    )
    try:
        result = paper_cut_only_split(image_bytes, enhance=enhance)
        logger.info(
            "POST /api/split-only 完成: %s 题",
            result.get("total_big_question_count"),
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("POST /api/split-only 失败: %s", exc)
        raise HTTPException(500, str(exc)) from exc


@app.post("/api/verify-vlm")
async def verify_vlm(file: UploadFile = File(...), model: str = Form("ernie-5.0")):
    """最小 VLM 连通性测试。"""
    image_bytes = await file.read()
    try:
        text = chat_vision(
            model=model,
            prompt="请用一句话描述图片内容。",
            image_bytes=image_bytes,
        )
        return {"ok": True, "model": model, "content": text}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "model": model, "error": str(exc)}


@app.post("/api/verify-structure-prompt")
async def verify_structure_prompt(
    file: UploadFile = File(...),
    model: str = Form("ernie-5.0"),
    enable_knowledge_points: bool = Form(False),
):
    """单图结构化 Prompt 测试。"""
    image_bytes = await file.read()
    prompt = build_structure_prompt(enable_knowledge_points=enable_knowledge_points)
    try:
        from backend.clients.vlm_client import extract_json_from_text

        raw = chat_vision(model=model, prompt=prompt, image_bytes=image_bytes)
        parsed = extract_json_from_text(raw)
        return {"ok": True, "model": model, "raw": raw, "parsed": parsed}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "model": model, "error": str(exc)}
