from __future__ import annotations

import re
import random
from typing import Any

from app.core.config import settings
from app.core.ids import new_id
from app.repo import get_user_dir, insert_learning_event, list_resources, read_json, write_json
from app.services.path_progress import record_stage_answer
from app.services.resource_structure import extract_questions_json


def build_exercise_session(student_id: str, limit: int = 12, resource_ids: list[str] | None = None, refresh_seed: int = 0) -> dict[str, Any]:
    records = _read_records(student_id)
    answered = {r.get("question_id"): r for r in records}
    generated_questions = _load_generated_questions(student_id, resource_ids=resource_ids) if resource_ids else []
    questions = generated_questions
    source_note = "generated_question_bank" if generated_questions else "no_generated_question_bank"

    capped_limit = max(1, min(limit, 50))
    question_pool = list(questions)
    rng = random.Random(f"{student_id}:{','.join(resource_ids or [])}:{refresh_seed}:{len(question_pool)}")
    rng.shuffle(question_pool)
    picked = question_pool[:capped_limit] if len(question_pool) > capped_limit else question_pool
    visible = []
    for question in picked:
        record = answered.get(question["id"])
        visible.append(
            {
                "id": question["id"],
                "source": question["source"],
                "type": question["type"],
                "stem": question["stem"],
                "options": question.get("options", []),
                "tags": _ensure_tags(question),
                "path_stage_id": question.get("path_stage_id", ""),
                "answered": bool(record),
                "last_answer": record.get("answer") if record else None,
                "last_correct": record.get("correct") if record else None,
                "last_correct_answer": record.get("correct_answer") if record else None,
                "last_analysis": record.get("analysis") if record else None,
            }
        )

    return {
        "source": source_note,
        "questions": visible,
        "stats": exercise_summary(student_id),
    }


def submit_exercise_answer(student_id: str, question_id: str, answer: Any) -> dict[str, Any]:
    questions = {q["id"]: q for q in _load_available_questions(student_id)}
    question = questions.get(question_id)
    if not question:
        question = next((record for record in reversed(_read_records(student_id)) if str(record.get("question_id")) == str(question_id)), None)
    if not question:
        raise ValueError("question_not_found")

    correct_answer = question.get("answer", question.get("correct_answer"))
    correct = _normalise_answer(answer) == _normalise_answer(correct_answer)
    record = {
        "id": new_id(),
        "question_id": question_id,
        "source": question.get("source", ""),
        "major": question.get("major") or "通用能力",
        "course": question.get("course") or "综合练习",
        "course_category": question.get("course_category") or "未分类课程",
        "chapter": question.get("chapter") or question.get("knowledge_point") or "",
        "knowledge_point": question.get("knowledge_point") or question.get("chapter") or "",
        "type": question.get("type", ""),
        "stem": question.get("stem", ""),
        "options": question.get("options", []),
        "answer": answer,
        "correct_answer": correct_answer,
        "correct": correct,
        "analysis": question.get("analysis", ""),
        "tags": _ensure_tags(question),
        "resource_id": question.get("resource_id", ""),
        "path_stage_id": question.get("path_stage_id", ""),
        "path_stage_title": question.get("path_stage_title", ""),
        "path_question_target": int(question.get("path_question_target") or 0),
    }

    records = _read_records(student_id)
    records.append(record)
    _write_records(student_id, records)
    path_progress = record_stage_answer(
        student_id,
        stage_id=str(question.get("path_stage_id") or ""),
        question_id=str(question_id),
        correct=correct,
        target_count=int(question.get("path_question_target") or 0),
        resource_id=str(question.get("resource_id") or ""),
    )
    insert_learning_event(
        student_id,
        "exercise_answer",
        {
            "question_id": question_id,
            "correct": correct,
            "tags": question.get("tags", []),
            "source": question.get("source", ""),
            "path_stage_id": question.get("path_stage_id", ""),
            "path_mastery": path_progress.get("mastery") if path_progress else None,
        },
    )

    return {
        "correct": correct,
        "correct_answer": correct_answer,
        "analysis": question.get("analysis", ""),
        "record": record,
        "stats": exercise_summary(student_id),
        "path_progress": path_progress,
    }


def delete_exercise_record(student_id: str, record_id: str) -> dict[str, Any]:
    records = _read_records(student_id)
    target = next((record for record in records if str(record.get("id")) == record_id), None)
    if not target:
        raise ValueError("record_not_found")
    target_question_id = str(target.get("question_id") or "")
    target_key = _wrong_record_key(target)
    kept = [
        record for record in records
        if not (
            str(record.get("id")) == record_id
            or (target_question_id and str(record.get("question_id")) == target_question_id and not record.get("correct"))
            or (target_key and _wrong_record_key(record) == target_key and not record.get("correct"))
        )
    ]
    _write_records(student_id, kept)
    insert_learning_event(student_id, "exercise_wrong_deleted", {"record_id": record_id, "question_id": target_question_id})
    return wrong_book_summary(student_id)


def delete_all_wrong_records(student_id: str) -> dict[str, Any]:
    summary = wrong_book_summary(student_id)
    wrong_record_ids = {str(record.get("id")) for record in summary.get("records", []) if record.get("id")}
    wrong_question_ids = {str(record.get("question_id")) for record in summary.get("records", []) if record.get("question_id")}
    wrong_keys = {_wrong_record_key(record) for record in summary.get("records", []) if _wrong_record_key(record)}
    if not wrong_record_ids:
        return summary
    records = _read_records(student_id)
    kept = [
        record for record in records
        if str(record.get("id")) not in wrong_record_ids
        and not (str(record.get("question_id")) in wrong_question_ids and not record.get("correct"))
        and not (_wrong_record_key(record) in wrong_keys and not record.get("correct"))
    ]
    _write_records(student_id, kept)
    insert_learning_event(student_id, "exercise_wrong_deleted_all", {"count": len(wrong_record_ids)})
    return wrong_book_summary(student_id)


def exercise_summary(student_id: str) -> dict[str, Any]:
    records = _read_records(student_id)
    total = len(records)
    correct = len([r for r in records if r.get("correct")])
    wrong = total - correct
    accuracy = round(correct * 100 / total, 1) if total else 0

    tag_stats: dict[str, dict[str, int]] = {}
    corrections = []
    for record in records:
        tags = _ensure_tags(record)
        for tag in tags:
            item = tag_stats.setdefault(str(tag), {"total": 0, "wrong": 0})
            item["total"] += 1
            if not record.get("correct"):
                item["wrong"] += 1
        if not record.get("correct"):
            corrections.append(record)

    weak_tags = sorted(
        [
            {
                "tag": tag,
                "total": stat["total"],
                "wrong": stat["wrong"],
                "wrong_rate": round(stat["wrong"] * 100 / stat["total"], 1) if stat["total"] else 0,
            }
            for tag, stat in tag_stats.items()
            if stat["wrong"] > 0
        ],
        key=lambda x: (x["wrong_rate"], x["wrong"]),
        reverse=True,
    )

    return {
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "accuracy": accuracy,
        "weak_tags": weak_tags[:8],
        "corrections": corrections[-10:],
    }


def wrong_book_summary(student_id: str) -> dict[str, Any]:
    records = _read_records(student_id)
    try:
        questions = {q["id"]: q for q in _load_available_questions(student_id)}
    except Exception:
        questions = {}
    latest_by_question: dict[str, dict[str, Any]] = {}
    for record in records:
        record_key = _wrong_record_key(record)
        if record_key:
            latest_by_question[record_key] = record

    wrong_records = []
    for record in latest_by_question.values():
        try:
            if not isinstance(record, dict) or record.get("correct"):
                continue
            question = questions.get(str(record.get("question_id")), {})
            options = record.get("options") or question.get("options", [])
            if not options and str(record.get("type") or question.get("type") or "") == "true_false":
                options = ["A. 正确", "B. 错误"]
            enriched = {
                **question,
                **record,
                "options": options,
                "tags": _ensure_tags({**question, **record}),
                "major": record.get("major") or question.get("major") or "通用能力",
                "course": record.get("course") or question.get("course") or "综合练习",
                "course_category": record.get("course_category") or question.get("course_category") or "未分类课程",
                "knowledge_point": record.get("knowledge_point") or record.get("chapter") or question.get("knowledge_point") or question.get("chapter") or "",
            }
            wrong_records.append(enriched)
        except Exception:
            continue

    grouped: dict[str, dict[str, Any]] = {}
    for record in wrong_records:
        major = str(record.get("major") or "通用能力")
        course = str(record.get("course") or "综合练习")
        major_group = grouped.setdefault(major, {"major": major, "count": 0, "courses": {}})
        course_group = major_group["courses"].setdefault(course, {"course": course, "count": 0, "items": []})
        major_group["count"] += 1
        course_group["count"] += 1
        course_group["items"].append(record)

    groups = []
    for major_group in grouped.values():
        courses = list(major_group["courses"].values())
        courses.sort(key=lambda item: item["course"])
        groups.append({"major": major_group["major"], "count": major_group["count"], "courses": courses})
    groups.sort(key=lambda item: item["major"])

    return {
        "groups": groups,
        "records": wrong_records,
        "ability_radar": _ability_radar(records),
        "tag_summary": _tag_summary(wrong_records),
        "stats": exercise_summary(student_id),
    }


def _load_available_questions(student_id: str) -> list[dict[str, Any]]:
    return _load_generated_questions(student_id)


def _wrong_record_key(record: dict[str, Any]) -> str:
    stem = re.sub(r"\s+", "", str(record.get("stem") or "")).lower()
    if stem:
        return f"stem:{stem}"
    question_id = str(record.get("question_id") or "").strip()
    return f"question:{question_id}" if question_id else ""


def _load_generated_questions(student_id: str, resource_ids: list[str] | None = None) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    selected_resource_ids = {str(resource_id) for resource_id in resource_ids or [] if str(resource_id).strip()}
    for resource in list_resources(student_id):
        try:
            if resource.get("type") != "question_bank":
                continue
            requirement = (resource.get("meta") or {}).get("requirement") or {}
            constraints = requirement.get("constraints") or {}
            if str(constraints.get("source") or "") not in {"exercise_custom_bank", "path_stage_quiz"}:
                continue
            if selected_resource_ids and str(resource.get("id")) not in selected_resource_ids:
                continue
            path = settings.data_path / str(resource.get("content_uri", ""))
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            payload = extract_questions_json(content)
            if isinstance(payload, dict):
                raw_questions = payload.get("questions") or []
            elif isinstance(payload, list):
                raw_questions = payload
            else:
                raw_questions = []
            for idx, raw in enumerate(raw_questions):
                if not isinstance(raw, dict):
                    continue
                questions.append(
                    _normalise_question(
                        raw,
                        f"generated:{resource.get('id')}:{idx}",
                        resource.get("title", ""),
                        payload if isinstance(payload, dict) else {},
                        requirement=requirement,
                        resource_id=str(resource.get("id") or ""),
                        question_count=len(raw_questions),
                    )
                )
        except Exception:
            continue
    return questions


def _normalise_question(
    raw: dict[str, Any],
    question_id: str,
    source: str,
    payload: dict[str, Any] | None = None,
    *,
    requirement: dict[str, Any] | None = None,
    resource_id: str = "",
    question_count: int = 0,
) -> dict[str, Any]:
    meta = payload.get("meta", {}) if isinstance(payload, dict) and isinstance(payload.get("meta"), dict) else {}
    requirement = requirement if isinstance(requirement, dict) else {}
    constraints = requirement.get("constraints") if isinstance(requirement.get("constraints"), dict) else {}
    question_config = requirement.get("question_config") if isinstance(requirement.get("question_config"), dict) else {}
    options, answer = _normalise_options_and_answer(raw.get("options"), raw.get("answer"))
    return {
        "id": question_id,
        "source": source or "generated_question_bank",
        "major": str(meta.get("major") or raw.get("major") or "通用能力"),
        "course": str(meta.get("course") or raw.get("course") or "综合练习"),
        "course_category": str(meta.get("course_category") or raw.get("course_category") or "未分类课程"),
        "chapter": str(meta.get("chapter") or raw.get("chapter") or ""),
        "knowledge_point": str(raw.get("knowledge_point") or meta.get("specific_knowledge_point") or meta.get("chapter") or ""),
        "type": str(raw.get("type") or "question"),
        "stem": str(raw.get("stem") or raw.get("question") or ""),
        "options": options,
        "answer": answer,
        "analysis": str(raw.get("analysis") or raw.get("explanation") or ""),
        "tags": _ensure_tags(raw),
        "difficulty": raw.get("difficulty") or question_config.get("difficulty") or constraints.get("difficulty") or "mixed",
        "resource_id": resource_id,
        "path_stage_id": str(constraints.get("path_stage_id") or ""),
        "path_stage_title": str(constraints.get("path_stage_title") or ""),
        "path_question_target": max(1, int(question_count or question_config.get("count") or 1)),
    }


def _ensure_tags(item: dict[str, Any]) -> list[str]:
    tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()] if isinstance(item.get("tags"), list) else []
    if tags:
        return tags[:6]
    text = f"{item.get('stem', '')} {item.get('analysis', '')} {item.get('knowledge_point', '')}"
    generated = []
    tag_rules = [
        ("概念辨析", ["定义", "概念", "区别", "混淆", "边界"]),
        ("逻辑推理", ["推理", "判断", "条件", "因果", "分析"]),
        ("运算处理", ["计算", "公式", "数值", "代入", "单位"]),
        ("抽象概括", ["抽象", "归纳", "模型", "概括", "结构"]),
        ("应用迁移", ["场景", "案例", "应用", "实际", "业务"]),
        ("流程规划", ["步骤", "流程", "顺序", "路径", "过程"]),
    ]
    for tag, keywords in tag_rules:
        if any(keyword in text for keyword in keywords):
            generated.append(tag)
    question_type = str(item.get("type") or "")
    type_tag = {
        "single_choice": "基础知识",
        "multiple_choice": "综合判断",
        "true_false": "概念辨析",
        "blank": "知识记忆",
        "short_answer": "表达概括",
        "case_analysis": "应用迁移",
        "calculation": "运算处理",
        "matching": "关联匹配",
        "ordering": "流程规划",
    }.get(question_type)
    if type_tag:
        generated.append(type_tag)
    return list(dict.fromkeys(generated or ["未分类"]))[:6]


def _tag_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, int]] = {}
    for record in records:
        for tag in _ensure_tags(record):
            item = summary.setdefault(tag, {"total": 0, "wrong": 0})
            item["total"] += 1
            if not record.get("correct"):
                item["wrong"] += 1
    return sorted(
        [
            {
                "tag": tag,
                "total": stat["total"],
                "wrong": stat["wrong"],
                "score": round(100 - stat["wrong"] * 100 / stat["total"], 1) if stat["total"] else 100,
            }
            for tag, stat in summary.items()
        ],
        key=lambda item: (item["score"], -item["total"]),
    )


def _ability_radar(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dimensions = [
        ("基础知识掌握能力", ["基础知识", "知识记忆", "概念辨析", "未分类", "定义", "判断", "填空"]),
        ("逻辑思维", ["逻辑推理", "综合判断", "流程规划", "推理", "排序", "多选", "multiple_choice", "ordering"]),
        ("运算处理能力", ["运算处理", "计算题", "计算", "公式", "数值", "calculation"]),
        ("抽象概括能力", ["抽象概括", "表达概括", "建模", "设计", "结构", "归纳", "short_answer", "case_analysis"]),
        ("应用迁移能力", ["应用迁移", "案例分析", "案例", "场景", "项目", "实践", "case_analysis", "short_answer", "calculation", "ordering"]),
        ("错因复盘能力", ["关联匹配", "流程规划", "概念辨析", "错因", "纠错", "复盘"]),
    ]
    result = []
    overall_score = _dimension_score(records)
    previous_overall_score = _dimension_score(records[:-1]) if records else 0.0
    for name, related_tags in dimensions:
        matched = _dimension_records(records, related_tags)
        inferred = bool(records and not matched)
        score = round(overall_score * 0.78, 1) if inferred else _dimension_score(matched)
        old_score = round(previous_overall_score * 0.78, 1) if inferred else (_dimension_score(matched[:-1]) if matched else 0.0)
        result.append(
            {
                "name": name,
                "score": score,
                "old_score": old_score,
                "total": len(matched),
                "basis": "综合答题表现推断" if inferred else "对应题型与标签证据",
            }
        )
    return result


def _dimension_records(records: list[dict[str, Any]], related_tags: list[str]) -> list[dict[str, Any]]:
    matched = []
    for record in records:
        tags = set(_ensure_tags(record))
        question_type = str(record.get("type") or "")
        searchable = " ".join(
            [
                question_type,
                str(record.get("stem") or ""),
                str(record.get("analysis") or ""),
                str(record.get("knowledge_point") or ""),
                *[str(tag) for tag in tags],
            ]
        )
        if tags.intersection(related_tags) or question_type in related_tags or any(tag in searchable for tag in related_tags):
            matched.append(record)
    # General questions often arrive without fine-grained tags. The basic and
    # review dimensions still need to reflect every genuine answer event.
    if not matched and records and ("基础知识" in related_tags or "错因" in related_tags):
        matched = list(records)
    return matched


def _dimension_score(records: list[dict[str, Any]]) -> float:
    if not records:
        return 0.0
    correct = len([record for record in records if record.get("correct")])
    # A small Beta(1,1) prior avoids an all-zero radar after the learner's
    # first wrong answer while still converging quickly to observed accuracy.
    return round((correct + 1) * 100 / (len(records) + 2), 1)


def _normalise_options(value: Any) -> list[str]:
    options, _ = _normalise_options_and_answer(value, None)
    return options


def _normalise_options_and_answer(options_value: Any, answer_value: Any) -> tuple[list[str], Any]:
    if not isinstance(options_value, list):
        return [], answer_value

    expanded: list[str] = []
    for option in options_value:
        text = str(option or "").strip()
        if not text:
            continue
        parts = _split_option_line(text)
        expanded.extend(parts or [text])

    label_to_new: dict[str, str] = {}
    fingerprint_to_label: dict[str, str] = {}
    seen_content: set[str] = set()
    cleaned: list[str] = []
    for raw in expanded:
        match = re.match(r"^([A-Ha-h])(?:[.、．)）:：]\s*|\s+)(.*)$", raw.strip())
        old_label = match.group(1).upper() if match else ""
        content = (match.group(2) if match else raw).strip()
        if not content:
            continue
        fingerprint = re.sub(r"\s+", "", content).lower()
        if fingerprint in seen_content:
            if old_label and fingerprint in fingerprint_to_label:
                label_to_new[old_label] = fingerprint_to_label[fingerprint]
            continue
        new_label = chr(ord("A") + len(cleaned))
        if old_label and old_label not in label_to_new:
            label_to_new[old_label] = new_label
        seen_content.add(fingerprint)
        fingerprint_to_label[fingerprint] = new_label
        cleaned.append(f"{new_label}. {content}")

    return cleaned, _remap_answer(answer_value, label_to_new)


def _split_option_line(text: str) -> list[str]:
    matches = list(re.finditer(r"(?<![A-Za-z])([A-Ha-h])(?:[.、．)）:：]\s*|\s+(?=\S))", text))
    if len(matches) <= 1:
        return [text]
    return [text[match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip() for index, match in enumerate(matches) if text[match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip()]


def _remap_answer(value: Any, label_to_new: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [label_to_new.get(str(item).strip().upper(), str(item).strip().upper()) for item in value]
    raw = str(value or "").strip()
    if re.fullmatch(r"[A-Ha-h](?:\s*[,，]\s*[A-Ha-h])*", raw):
        labels = re.split(r"\s*[,，]\s*", raw.upper())
        mapped = [label_to_new.get(label, label) for label in labels if label]
        return ",".join(mapped)
    return value


def _normalise_answer(value: Any) -> str:
    if isinstance(value, list):
        labels = [str(x).strip().upper() for x in value if str(x).strip()]
        if labels and all(re.fullmatch(r"[A-H]", label) for label in labels):
            return "".join(sorted(labels))
        return "".join(sorted(labels))
    raw = re.sub(r"\s+", "", str(value or "").strip().upper().replace("，", ",").replace("、", ","))
    if raw and re.fullmatch(r"[A-H](?:,?[A-H])*", raw):
        return "".join(sorted(re.findall(r"[A-H]", raw)))
    return raw


def _records_path(student_id: str):
    return get_user_dir(student_id) / "exercise_records.json"


def _read_records(student_id: str) -> list[dict[str, Any]]:
    data = read_json(_records_path(student_id), [])
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _write_records(student_id: str, records: list[dict[str, Any]]) -> None:
    write_json(_records_path(student_id), records)
