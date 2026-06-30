"""教育文档解析主流水线。"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from backend.clients.baidu_ocr import paper_cut_only_split
from backend.clients.vlm_client import chat_vision, extract_json_from_text
from backend.prompts.structure import build_structure_prompt
from backend.utils.image_tools import (
    crop_by_box,
    crop_origin,
    image_to_base64,
    load_image,
    offset_structure_to_origin,
)

logger = logging.getLogger(__name__)


def _parse_single_question(
    *,
    image_bytes: bytes,
    question: dict,
    model: str,
    enable_knowledge_points: bool,
) -> dict[str, Any]:
    big_q_idx = question.get("big_q_idx")
    split_box = question.get("split_box")
    if not split_box:
        logger.warning("题 %s 无有效 split_box，跳过 VLM", big_q_idx)
        return {
            "big_q_idx": big_q_idx,
            "parse_status": "FAILED",
            "error": "无有效切题框",
            "split_box": None,
            "handwrite_boxes": question.get("handwrite_boxes", []),
            "pic_boxes": question.get("pic_boxes", []),
            "structure": None,
        }

    image = load_image(image_bytes)
    crop = crop_by_box(image, split_box)
    origin_x, origin_y = crop_origin(split_box)

    from io import BytesIO

    buf = BytesIO()
    crop.save(buf, format="JPEG", quality=92)
    crop_bytes = buf.getvalue()

    prompt = build_structure_prompt(
        enable_knowledge_points=enable_knowledge_points,
        crop_width=crop.width,
        crop_height=crop.height,
    )
    crop_kb = len(crop_bytes) / 1024
    logger.info(
        "题 %s VLM 开始: model=%s crop=%.0fx%.0f (%.1f KB)",
        big_q_idx,
        model,
        crop.width,
        crop.height,
        crop_kb,
    )
    t0 = time.perf_counter()
    try:
        raw_text = chat_vision(model=model, prompt=prompt, image_bytes=crop_bytes)
        structure = extract_json_from_text(raw_text)
        structure = offset_structure_to_origin(
            structure,
            origin_x,
            origin_y,
            crop_w=crop.width,
            crop_h=crop.height,
            image_w=image.width,
            image_h=image.height,
        )
        sub_count = len(structure.get("sub_questions", []))
        logger.info(
            "题 %s VLM 成功: 耗时 %.2fs, 子题数=%s, title=%s",
            big_q_idx,
            time.perf_counter() - t0,
            sub_count,
            (structure.get("big_q_title") or "")[:40],
        )
        return {
            "big_q_idx": big_q_idx,
            "qus_id": question.get("qus_id"),
            "parse_status": "SUCCESS",
            "split_box": split_box,
            "qus_boxes": question.get("qus_boxes", []),
            "handwrite_boxes": question.get("handwrite_boxes", []),
            "pic_boxes": question.get("pic_boxes", []),
            "crop_base64": image_to_base64(crop),
            "structure": structure,
            "vlm_raw": raw_text,
        }
    except Exception as exc:  # noqa: BLE001 - demo 需捕获单题失败
        logger.error("题 %s VLM 失败 (%.2fs): %s", big_q_idx, time.perf_counter() - t0, exc)
        return {
            "big_q_idx": big_q_idx,
            "qus_id": question.get("qus_id"),
            "parse_status": "FAILED",
            "error": str(exc),
            "split_box": split_box,
            "qus_boxes": question.get("qus_boxes", []),
            "handwrite_boxes": question.get("handwrite_boxes", []),
            "pic_boxes": question.get("pic_boxes", []),
            "structure": None,
        }


def run_pipeline(
    image_bytes: bytes,
    *,
    model: str = "ernie-5.0",
    enable_knowledge_points: bool = False,
    enhance: bool = False,
    skip_vlm: bool = False,
    max_questions: int | None = 3,
) -> dict[str, Any]:
    request_id = str(uuid.uuid4())
    pipeline_t0 = time.perf_counter()

    image = load_image(image_bytes)
    logger.info(
        "流水线开始 request_id=%s image=%sx%s (%.1f KB) model=%s enhance=%s skip_vlm=%s max_questions=%s",
        request_id,
        image.width,
        image.height,
        len(image_bytes) / 1024,
        model,
        enhance,
        skip_vlm,
        max_questions,
    )

    ocr_t0 = time.perf_counter()
    split = paper_cut_only_split(image_bytes, enhance=enhance)
    logger.info(
        "OCR 切题完成: 耗时 %.2fs, 检出 %s 题 (api_count=%s)",
        time.perf_counter() - ocr_t0,
        len(split["big_question_list"]),
        split.get("total_big_question_count"),
    )

    questions = split["big_question_list"]

    if max_questions is not None:
        if len(questions) > max_questions:
            logger.info("题目截断: %s → %s (max_questions)", len(questions), max_questions)
        questions = questions[:max_questions]

    for q in questions:
        if q.get("split_box"):
            crop = crop_by_box(image, q["split_box"])
            q["crop_base64"] = image_to_base64(crop)

    parsed_questions: list[dict] = []
    if skip_vlm:
        logger.info("skip_vlm=true，跳过 %s 道题的 VLM 结构化", len(questions))
        for q in questions:
            parsed_questions.append(
                {
                    "big_q_idx": q.get("big_q_idx"),
                    "qus_id": q.get("qus_id"),
                    "parse_status": "SKIPPED",
                    "split_box": q.get("split_box"),
                    "qus_boxes": q.get("qus_boxes", []),
                    "handwrite_boxes": q.get("handwrite_boxes", []),
                    "pic_boxes": q.get("pic_boxes", []),
                    "crop_base64": q.get("crop_base64"),
                    "structure": None,
                }
            )
    else:
        logger.info("VLM 结构化开始: %s 道题, workers=2", len(questions))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(
                    _parse_single_question,
                    image_bytes=image_bytes,
                    question=q,
                    model=model,
                    enable_knowledge_points=enable_knowledge_points,
                ): q
                for q in questions
            }
            for fut in as_completed(futures):
                parsed_questions.append(fut.result())
        parsed_questions.sort(key=lambda x: x.get("big_q_idx", 0))

    success = sum(1 for q in parsed_questions if q.get("parse_status") == "SUCCESS")
    failed = sum(1 for q in parsed_questions if q.get("parse_status") == "FAILED")
    total_sub = sum(
        len(q.get("structure", {}).get("sub_questions", []))
        for q in parsed_questions
        if q.get("structure")
    )

    if not questions:
        job_status = "FAILED"
        logger.warning(
            "流水线结束 request_id=%s: NO_QUESTION_DETECTED (image=%sx%s, enhance=%s)",
            request_id,
            image.width,
            image.height,
            enhance,
        )
    elif failed and success:
        job_status = "PARTIAL"
    elif failed and not success:
        job_status = "FAILED" if not skip_vlm else "DONE"
    else:
        job_status = "DONE"

    logger.info(
        "流水线结束 request_id=%s status=%s 切题=%s 成功=%s 失败=%s 子题=%s 总耗时 %.2fs",
        request_id,
        job_status,
        len(questions),
        success,
        failed,
        total_sub,
        time.perf_counter() - pipeline_t0,
    )

    question_infos = []
    for q in parsed_questions:
        st = q.get("structure") or {}
        info = {
            "BigQIdx": q.get("big_q_idx"),
            "QusId": q.get("qus_id"),
            "ParseStatus": q.get("parse_status"),
            "SplitBox": q.get("split_box"),
            "QusBoxes": q.get("qus_boxes", []),
            "PicBoxes": q.get("pic_boxes", []),
            "OcrHandwriteBoxes": q.get("handwrite_boxes", []),
            "CropBase64": q.get("crop_base64"),
            "BigQTitle": st.get("big_q_title", ""),
            "BigQTitleBox": st.get("big_q_title_box"),
            "Subject": st.get("subject", ""),
            "QuestionType": st.get("question_type", ""),
            "KnowledgePoints": st.get("knowledge_points", []),
            "SubQuestions": st.get("sub_questions", []),
            "Error": q.get("error"),
        }
        question_infos.append(info)

    return {
        "RequestId": request_id,
        "Response": {
            "JobStatus": job_status,
            "ErrorCode": "" if questions else "NO_QUESTION_DETECTED",
            "ErrorMessage": "" if questions else "未检测到题目",
            "ImageWidth": image.width,
            "ImageHeight": image.height,
            "EnhanceUrl": split.get("enhance_url", ""),
            "Stats": {
                "total_big_questions": len(questions),
                "parsed_big_questions": success,
                "failed_big_questions": failed,
                "total_sub_questions": total_sub,
            },
            "QuestionInfos": question_infos,
            "SplitRaw": {
                "total_big_question_count": split["total_big_question_count"],
            },
        },
    }
