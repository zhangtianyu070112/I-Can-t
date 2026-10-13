from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.ids import new_id
from app.core.config import settings


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_user_dir(student_id: str) -> Path:
    user_dir = settings.data_path / "users" / student_id
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_student(*, student_id: str, major: str | None, goals: str | None) -> None:
    user_dir = get_user_dir(student_id)
    student_file = user_dir / "student.json"
    data = read_json(student_file, {})
    
    if not data:
        data = {
            "id": student_id,
            "major": major or "",
            "grade": "",
            "goals": goals or "",
            "created_at": now_iso()
        }
    else:
        if major is not None:
            data["major"] = major
        if goals is not None:
            data["goals"] = goals
            
    write_json(student_file, data)


def insert_profile_snapshot(*, student_id: str, profile: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    user_dir = get_user_dir(student_id)
    profiles_file = user_dir / "profiles.json"
    profiles = read_json(profiles_file, [])
    
    snapshot_id = new_id()
    created_at = now_iso()
    
    snapshot = {
        "id": snapshot_id,
        "student_id": student_id,
        **profile,
        "evidence": evidence,
        "created_at": created_at
    }
    
    profiles.append(snapshot)
    write_json(profiles_file, profiles)
    return snapshot


def get_latest_profile_snapshot(student_id: str) -> dict[str, Any] | None:
    user_dir = get_user_dir(student_id)
    profiles_file = user_dir / "profiles.json"
    profiles = read_json(profiles_file, [])
    if not profiles:
        return None
    # 按创建时间降序
    profiles.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return profiles[0]


def insert_resource_item(
    *,
    student_id: str,
    type: str,
    title: str,
    tags: list[str],
    content_uri: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    user_dir = get_user_dir(student_id)
    resources_file = user_dir / "resources.json"
    resources = read_json(resources_file, [])
    
    resource_id = new_id()
    created_at = now_iso()
    
    item = {
        "id": resource_id,
        "student_id": student_id,
        "type": type,
        "title": title,
        "tags": tags,
        "content_uri": content_uri,
        "meta": meta,
        "created_at": created_at,
    }
    resources.append(item)
    write_json(resources_file, resources)
    return item


def get_resource_item(resource_id: str) -> dict[str, Any] | None:
    users_dir = settings.data_path / "users"
    if not users_dir.exists():
        return None
    for user_dir in users_dir.iterdir():
        if user_dir.is_dir():
            resources_file = user_dir / "resources.json"
            resources = read_json(resources_file, [])
            for r in resources:
                if r.get("id") == resource_id:
                    return r
    return None


def list_resources(student_id: str) -> list[dict[str, Any]]:
    user_dir = get_user_dir(student_id)
    resources_file = user_dir / "resources.json"
    resources = read_json(resources_file, [])
    resources.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return resources


def insert_learning_event(student_id: str, event_type: str, payload: dict[str, Any]) -> None:
    user_dir = get_user_dir(student_id)
    events_file = user_dir / "events.json"
    events = read_json(events_file, [])
    
    events.append({
        "id": new_id(),
        "student_id": student_id,
        "event_type": event_type,
        "payload": payload,
        "created_at": now_iso()
    })
    write_json(events_file, events)


def insert_resource_usage(
    *, student_id: str, resource_id: str, action: str, duration_sec: int | None, feedback: dict[str, Any]
) -> None:
    user_dir = get_user_dir(student_id)
    usage_file = user_dir / "usage.json"
    usages = read_json(usage_file, [])
    
    usages.append({
        "id": new_id(),
        "resource_id": resource_id,
        "student_id": student_id,
        "action": action,
        "duration_sec": duration_sec,
        "feedback": feedback,
        "created_at": now_iso()
    })
    write_json(usage_file, usages)


def get_user_events(student_id: str) -> list[dict[str, Any]]:
    """获取用户的所有学习事件（用于潜在问题发现等场景）"""
    user_dir = get_user_dir(student_id)
    events_file = user_dir / "events.json"
    return read_json(events_file, [])


def get_user_usages(student_id: str) -> list[dict[str, Any]]:
    """获取用户的资源使用记录（包含反馈信息）"""
    user_dir = get_user_dir(student_id)
    usage_file = user_dir / "usage.json"
    return read_json(usage_file, [])
