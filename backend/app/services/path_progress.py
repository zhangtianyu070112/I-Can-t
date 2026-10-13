from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.ids import new_id
from app.repo import get_user_dir, get_user_events, read_json, write_json


PASS_THRESHOLD = 80


def overlay_path_progress(
    student_id: str,
    *,
    plan_key: str,
    nodes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Overlay persisted exercise progress on the latest generated learning path."""
    state = _ensure_state(student_id, plan_key=plan_key, nodes=nodes)
    stage_state = state.get("stages", {})
    branches = state.get("branches") if isinstance(state.get("branches"), list) else []
    enriched: list[dict[str, Any]] = []
    for node in nodes:
        stage_id = str(node.get("id") or "")
        progress = stage_state.get(stage_id, {}) if isinstance(stage_state, dict) else {}
        bank_ids = [str(item) for item in progress.get("question_bank_ids", []) if str(item)]
        enriched.append(
            {
                **node,
                "status": progress.get("status") or node.get("status") or "locked",
                "mastery": int(progress.get("mastery") or 0),
                "answered_count": int(progress.get("answered_count") or 0),
                "correct_count": int(progress.get("correct_count") or 0),
                "target_count": int(progress.get("target_count") or 0),
                "accuracy": float(progress.get("accuracy") or 0),
                "question_bank_ids": bank_ids,
                "active_question_bank_id": str(progress.get("active_question_bank_id") or ""),
                "branches": [item for item in branches if str(item.get("parent_id") or "") == stage_id],
            }
        )
    return enriched, _public_state(state)


def add_path_branch(
    student_id: str,
    *,
    knowledge_node_id: str,
    title: str,
    description: str = "",
    mastery: float = 0,
) -> dict[str, Any]:
    plan_key, nodes = _latest_path_context(student_id)
    if not nodes:
        raise ValueError("请先生成学习路径，再加入知识分支。")
    state = _ensure_state(student_id, plan_key=plan_key, nodes=nodes)
    stages = state.get("stages") if isinstance(state.get("stages"), dict) else {}
    parent_id = str(state.get("current_stage_id") or "")
    if not parent_id:
        parent_id = next(
            (
                str(node.get("id") or "")
                for node in nodes
                if str((stages.get(str(node.get("id") or "")) or {}).get("status") or "")
                in {"current", "warning"}
            ),
            str(nodes[-1].get("id") or ""),
        )
    parent = next((node for node in nodes if str(node.get("id") or "") == parent_id), nodes[-1])
    branches = state.get("branches") if isinstance(state.get("branches"), list) else []
    existing = next(
        (
            item for item in branches
            if str(item.get("parent_id") or "") == parent_id
            and str(item.get("knowledge_node_id") or "") == knowledge_node_id
        ),
        None,
    )
    if isinstance(existing, dict):
        return {"branch": existing, "parent_stage": parent, "created": False}

    branch = {
        "id": f"branch-{new_id()}",
        "parent_id": parent_id,
        "knowledge_node_id": knowledge_node_id,
        "title": title.strip() or "知识补充分支",
        "goal": description.strip() or f"补充学习“{title.strip() or '当前知识点'}”",
        "status": "branch",
        "mastery": max(0, min(100, round(float(mastery or 0), 1))),
        "resources": ["lecture_doc", "question_bank"],
        "source": "knowledge_hub",
        "created_at": _now_iso(),
    }
    branches.append(branch)
    state["branches"] = branches[-40:]
    state["updated_at"] = _now_iso()
    _write_state(student_id, state)
    return {"branch": branch, "parent_stage": parent, "created": True}


def register_stage_question_bank(
    student_id: str,
    *,
    stage_id: str,
    resource_id: str,
    target_count: int,
) -> dict[str, Any]:
    plan_key, nodes = _latest_path_context(student_id)
    state = _ensure_state(student_id, plan_key=plan_key, nodes=nodes)
    stages = state.setdefault("stages", {})
    stage = stages.get(stage_id)
    if not isinstance(stage, dict):
        raise ValueError("path_stage_not_found")
    if stage.get("status") == "locked":
        raise ValueError("path_stage_locked")

    bank_ids = [str(item) for item in stage.get("question_bank_ids", []) if str(item)]
    if resource_id not in bank_ids:
        bank_ids.append(resource_id)
    stage.update(
        {
            "question_bank_ids": bank_ids[-8:],
            "active_question_bank_id": resource_id,
            "target_count": max(1, min(50, int(target_count or 1))),
            "answers": {},
            "answered_count": 0,
            "correct_count": 0,
            "accuracy": 0,
            "mastery": 0,
            "status": "current",
            "updated_at": _now_iso(),
        }
    )
    state["updated_at"] = _now_iso()
    _write_state(student_id, state)
    return _stage_result(state, stage_id, advanced=False)


def record_stage_answer(
    student_id: str,
    *,
    stage_id: str,
    question_id: str,
    correct: bool,
    target_count: int = 0,
    resource_id: str = "",
) -> dict[str, Any] | None:
    if not stage_id:
        return None

    plan_key, nodes = _latest_path_context(student_id)
    state = _ensure_state(student_id, plan_key=plan_key, nodes=nodes)
    stages = state.setdefault("stages", {})
    stage = stages.get(stage_id)
    if not isinstance(stage, dict):
        return None

    active_bank_id = str(stage.get("active_question_bank_id") or "")
    if resource_id and active_bank_id and resource_id != active_bank_id:
        return _stage_result(state, stage_id, advanced=False)

    if resource_id and not active_bank_id:
        stage["active_question_bank_id"] = resource_id
        bank_ids = [str(item) for item in stage.get("question_bank_ids", []) if str(item)]
        if resource_id not in bank_ids:
            bank_ids.append(resource_id)
        stage["question_bank_ids"] = bank_ids[-8:]

    if target_count:
        stage["target_count"] = max(1, min(50, int(target_count)))
    target = max(1, int(stage.get("target_count") or target_count or 1))
    answers = stage.get("answers") if isinstance(stage.get("answers"), dict) else {}
    answers[str(question_id)] = bool(correct)
    answered_count = len(answers)
    correct_count = sum(1 for value in answers.values() if value is True)
    accuracy = round(correct_count * 100 / answered_count, 1) if answered_count else 0.0
    mastery = min(100, round(correct_count * 100 / target))

    stage.update(
        {
            "answers": answers,
            "answered_count": answered_count,
            "correct_count": correct_count,
            "accuracy": accuracy,
            "mastery": mastery,
            "updated_at": _now_iso(),
        }
    )

    advanced = answered_count >= target and mastery >= PASS_THRESHOLD
    next_stage_id = ""
    if advanced:
        ordered_ids = [str(node.get("id") or "") for node in nodes]
        current_index = ordered_ids.index(stage_id) if stage_id in ordered_ids else -1
        stage["status"] = "completed"
        stage["mastery"] = max(PASS_THRESHOLD, mastery)
        if 0 <= current_index < len(ordered_ids) - 1:
            next_stage_id = ordered_ids[current_index + 1]
            next_stage = stages.get(next_stage_id)
            if isinstance(next_stage, dict) and next_stage.get("status") != "completed":
                next_stage["status"] = "current"
        state["current_stage_id"] = next_stage_id
    elif answered_count >= target:
        stage["status"] = "warning"
        state["current_stage_id"] = stage_id
    else:
        stage["status"] = "current"
        state["current_stage_id"] = stage_id

    state["updated_at"] = _now_iso()
    _write_state(student_id, state)
    return _stage_result(state, stage_id, advanced=advanced, next_stage_id=next_stage_id)


def _ensure_state(student_id: str, *, plan_key: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    state = read_json(_state_path(student_id), {})
    if not isinstance(state, dict) or str(state.get("plan_key") or "") != str(plan_key or ""):
        state = _new_state(plan_key=plan_key, nodes=nodes)
        _write_state(student_id, state)
        return state

    stages = state.setdefault("stages", {})
    if not isinstance(stages, dict):
        stages = {}
        state["stages"] = stages
    changed = False
    for index, node in enumerate(nodes):
        stage_id = str(node.get("id") or f"stage-{index + 1}")
        if stage_id in stages and isinstance(stages[stage_id], dict):
            continue
        stages[stage_id] = _empty_stage(
            stage_id,
            str(node.get("status") or ("current" if index == 0 else "locked")),
        )
        changed = True
    if changed:
        _write_state(student_id, state)
    return state


def _new_state(*, plan_key: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    stages: dict[str, Any] = {}
    has_current = False
    for index, node in enumerate(nodes):
        stage_id = str(node.get("id") or f"stage-{index + 1}")
        raw_status = str(node.get("status") or "")
        if raw_status in {"completed", "done"}:
            status = "completed"
        elif not has_current and raw_status in {"current", "active", "warning"}:
            status = "current"
            has_current = True
        elif index == 0 and not has_current:
            status = "current"
            has_current = True
        else:
            status = "locked"
        stages[stage_id] = _empty_stage(stage_id, status)
    current_stage_id = next((key for key, value in stages.items() if value.get("status") == "current"), "")
    return {
        "version": 1,
        "plan_key": str(plan_key or ""),
        "pass_threshold": PASS_THRESHOLD,
        "current_stage_id": current_stage_id,
        "stages": stages,
        "branches": [],
        "updated_at": _now_iso(),
    }


def _empty_stage(stage_id: str, status: str) -> dict[str, Any]:
    return {
        "id": stage_id,
        "status": status,
        "mastery": 100 if status == "completed" else 0,
        "answered_count": 0,
        "correct_count": 0,
        "target_count": 0,
        "accuracy": 0,
        "answers": {},
        "question_bank_ids": [],
        "active_question_bank_id": "",
    }


def _latest_path_context(student_id: str) -> tuple[str, list[dict[str, Any]]]:
    events = [item for item in get_user_events(student_id) if item.get("event_type") == "path_plan"]
    latest = events[-1] if events else {}
    payload = latest.get("payload") if isinstance(latest.get("payload"), dict) else {}
    raw_path = payload.get("path") or payload.get("plan") or {}
    path = raw_path if isinstance(raw_path, dict) else {}
    raw_nodes = path.get("nodes") or path.get("steps") or payload.get("nodes") or []
    nodes = _normalize_nodes(raw_nodes)
    return str(latest.get("id") or latest.get("created_at") or ""), nodes


def _normalize_nodes(raw_nodes: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_nodes, list):
        return []
    nodes: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            continue
        step = raw.get("step") or raw.get("order") or index + 1
        nodes.append(
            {
                **raw,
                "id": raw.get("id") or f"stage-{step}",
                "step": step,
                "status": raw.get("status") or ("current" if not nodes else "locked"),
            }
        )
    return nodes


def _stage_result(
    state: dict[str, Any],
    stage_id: str,
    *,
    advanced: bool,
    next_stage_id: str = "",
) -> dict[str, Any]:
    stage = (state.get("stages") or {}).get(stage_id, {})
    return {
        "stage_id": stage_id,
        "status": stage.get("status", "current"),
        "mastery": int(stage.get("mastery") or 0),
        "answered_count": int(stage.get("answered_count") or 0),
        "correct_count": int(stage.get("correct_count") or 0),
        "target_count": int(stage.get("target_count") or 0),
        "accuracy": float(stage.get("accuracy") or 0),
        "pass_threshold": int(state.get("pass_threshold") or PASS_THRESHOLD),
        "advanced": advanced,
        "next_stage_id": next_stage_id,
        "message": (
            "本阶段已达标，下一学习阶段已自动解锁。"
            if advanced and next_stage_id
            else "全部学习阶段已完成。"
            if advanced
            else "本轮已完成，掌握度未达 80%，请订正错题后继续。"
            if int(stage.get("answered_count") or 0) >= int(stage.get("target_count") or 1)
            else "阶段掌握度已更新。"
        ),
    }


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "pass_threshold": int(state.get("pass_threshold") or PASS_THRESHOLD),
        "current_stage_id": str(state.get("current_stage_id") or ""),
        "updated_at": str(state.get("updated_at") or ""),
    }


def _state_path(student_id: str):
    return get_user_dir(student_id) / "path_progress.json"


def _write_state(student_id: str, state: dict[str, Any]) -> None:
    write_json(_state_path(student_id), state)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
