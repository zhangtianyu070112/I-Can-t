from __future__ import annotations

import json
from typing import Any

from app.llm import get_llm_client_for, is_llm_configured
from app.repo import (
    get_latest_profile_snapshot,
    get_user_events,
    get_user_usages,
    insert_learning_event,
    insert_profile_snapshot,
)


PROFILE_KEYS = [
    "knowledge_base_level",
    "cognitive_style",
    "mistake_patterns",
    "modality_preference",
    "pace_preference",
    "motivation_style",
]


class EvolutionEngine:
    async def evaluate_and_evolve(
        self,
        student_id: str,
        trigger_event: str,
        context_data: dict[str, Any],
        *,
        dry_run: bool = False,
        decision_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current_profile = get_latest_profile_snapshot(student_id) or {}
        recent_events = get_user_events(student_id)[-8:]
        recent_usages = get_user_usages(student_id)[-8:]

        if decision_override:
            updates = decision_override.get("profile_updates") or {}
            decision = {
                "needs_evolution": bool(updates),
                "reason": decision_override.get("reason", ""),
                "recommended_action": decision_override.get("recommended_action", ""),
                "profile_updates": updates,
                "mode": decision_override.get("mode", "preview_replay"),
            }
        elif is_llm_configured("evaluate"):
            decision = await self._llm_decide(
                current_profile=current_profile,
                recent_events=recent_events,
                recent_usages=recent_usages,
                trigger_event=trigger_event,
                context_data=context_data,
            )
        else:
            decision = self._heuristic_decide(
                current_profile=current_profile,
                recent_events=recent_events,
                recent_usages=recent_usages,
                trigger_event=trigger_event,
                context_data=context_data,
            )

        if not decision.get("needs_evolution"):
            insert_learning_event(
                student_id,
                "evolution_skipped",
                {
                    "trigger": trigger_event,
                    "reason": decision.get("reason", "当前证据不足，不执行画像进化。"),
                    "dry_run": dry_run,
                },
            )
            return {
                "evolved": False,
                "trigger": trigger_event,
                "reason": decision.get("reason", ""),
                "recommended_action": decision.get("recommended_action", ""),
                "mode": decision.get("mode", "heuristic"),
            }

        updates = decision.get("profile_updates") or {}
        new_profile = self._merge_profile(current_profile, updates)
        evidence = self._merge_evidence(current_profile, updates, trigger_event, context_data)

        if dry_run:
            return {
                "evolved": False,
                "dry_run": True,
                "trigger": trigger_event,
                "reason": decision.get("reason", ""),
                "recommended_action": decision.get("recommended_action", ""),
                "profile_updates": updates,
                "preview_profile": new_profile,
                "mode": decision.get("mode", "heuristic"),
            }

        snapshot = insert_profile_snapshot(student_id=student_id, profile=new_profile, evidence=evidence)
        insert_learning_event(
            student_id,
            "evolution_triggered",
            {
                "trigger": trigger_event,
                "reason": decision.get("reason", ""),
                "recommended_action": decision.get("recommended_action", ""),
                "profile_updates": updates,
                "snapshot_id": snapshot["id"],
                "mode": decision.get("mode", "heuristic"),
            },
        )

        return {
            "evolved": True,
            "trigger": trigger_event,
            "reason": decision.get("reason", ""),
            "recommended_action": decision.get("recommended_action", ""),
            "profile_updates": updates,
            "new_profile_snapshot": snapshot,
            "mode": decision.get("mode", "heuristic"),
        }

    async def _llm_decide(
        self,
        *,
        current_profile: dict[str, Any],
        recent_events: list[dict[str, Any]],
        recent_usages: list[dict[str, Any]],
        trigger_event: str,
        context_data: dict[str, Any],
    ) -> dict[str, Any]:
        llm = get_llm_client_for("evaluate")
        schema_hint = (
            '{"needs_evolution": true, '
            '"reason": "为什么需要或不需要迭代", '
            '"recommended_action": "下一步动作建议", '
            '"profile_updates": {"knowledge_base_level": "", "mistake_patterns": "", '
            '"cognitive_style": "", "pace_preference": "", "modality_preference": "", "motivation_style": ""}}'
        )
        prompt = f"""
你是学习系统的自我监督与进化引擎。
你的任务是根据学生近期行为、资源反馈、测验表现和当前画像，判断是否需要动态调整学生画像和学习策略。

当前学生画像：
{json.dumps(current_profile, ensure_ascii=False)}

触发事件：
{trigger_event}

触发上下文：
{json.dumps(context_data, ensure_ascii=False)}

近期系统事件：
{json.dumps(recent_events, ensure_ascii=False)}

近期资源反馈：
{json.dumps(recent_usages, ensure_ascii=False)}

判断要求：
1. 如果负反馈、低分、反复提问或学习路径偏离说明当前画像/策略不匹配，needs_evolution=true。
2. profile_updates 只填写需要调整的画像字段，其余字段留空。
3. recommended_action 必须具体，例如降低难度、改推图解资源、补充某类练习、重新规划路径。
4. 不要夸大证据；证据不足时 needs_evolution=false。
"""
        data = await llm.chat_json(messages=[{"role": "user", "content": prompt}], schema_hint=schema_hint)
        if not isinstance(data, dict):
            return self._heuristic_decide(
                current_profile=current_profile,
                recent_events=recent_events,
                recent_usages=recent_usages,
                trigger_event=trigger_event,
                context_data=context_data,
            )
        data["mode"] = "llm"
        return data

    def _heuristic_decide(
        self,
        *,
        current_profile: dict[str, Any],
        recent_events: list[dict[str, Any]],
        recent_usages: list[dict[str, Any]],
        trigger_event: str,
        context_data: dict[str, Any],
    ) -> dict[str, Any]:
        trigger = trigger_event.lower().strip()
        action = str(context_data.get("action", "")).lower()
        score = _as_float(context_data.get("score"))
        resource_type = str(context_data.get("resource_type") or context_data.get("type") or "")
        topic = str(context_data.get("topic") or context_data.get("knowledge_point") or context_data.get("question") or "")
        recent_dislikes = len([u for u in recent_usages if str(u.get("action")).lower() == "dislike"])
        recent_tutor = [e for e in recent_events if e.get("event_type") == "tutor"]

        updates: dict[str, str] = {}
        reasons: list[str] = []
        recommended: list[str] = []

        if "quiz" in trigger or "assessment" in trigger or "mastery" in trigger or score is not None:
            if score is not None and score < 60:
                updates["knowledge_base_level"] = "基础薄弱，需要先补概念再练习"
                if topic:
                    updates["mistake_patterns"] = f"{topic} 掌握不足"
                updates["pace_preference"] = "慢节奏"
                reasons.append(f"最新测评/掌握度分数为 {score:g}，低于 60 分阈值。")
                recommended.append("降低下一阶段学习难度，优先推送讲解文档、思维导图和基础题。")

        if action == "dislike" or "negative" in trigger or "feedback" in trigger:
            updates["modality_preference"] = _fallback_modality(resource_type)
            updates["pace_preference"] = "需要更短步骤和更强示例支撑"
            reasons.append("学生对资源给出负反馈，说明资源形式、难度或解释方式可能不匹配。")
            recommended.append("降低同类资源排序，改推图解、案例化讲解或更细粒度练习。")

        if recent_dislikes >= 2:
            updates["motivation_style"] = "需要即时反馈和阶段性成就激励"
            reasons.append(f"近期已有 {recent_dislikes} 次资源点踩，说明推荐策略需要调整。")
            recommended.append("触发一次路径重排，并展示更明确的完成目标与验收标准。")

        if len(recent_tutor) >= 3:
            questions = "；".join(str(e.get("payload", {}).get("question", "")) for e in recent_tutor[-3:])
            updates["mistake_patterns"] = topic or questions[:80] or current_profile.get("mistake_patterns", "")
            reasons.append("近期多次触发智能辅导，反映当前学习路径中存在重复卡点。")
            recommended.append("把最近答疑主题加入下一轮路径规划和资源推送的优先级。")

        if not reasons:
            return {
                "needs_evolution": False,
                "reason": "当前反馈和学习行为没有达到画像进化阈值。",
                "recommended_action": "继续观察学习行为，等待更多测评、反馈或答疑数据。",
                "profile_updates": {},
                "mode": "heuristic",
            }

        return {
            "needs_evolution": True,
            "reason": "；".join(reasons),
            "recommended_action": "；".join(recommended),
            "profile_updates": updates,
            "mode": "heuristic",
        }

    def _merge_profile(self, current_profile: dict[str, Any], updates: dict[str, Any]) -> dict[str, str]:
        merged: dict[str, str] = {}
        for key in PROFILE_KEYS:
            value = updates.get(key)
            merged[key] = str(value or current_profile.get(key, "") or "")
        return merged

    def _merge_evidence(
        self,
        current_profile: dict[str, Any],
        updates: dict[str, Any],
        trigger_event: str,
        context_data: dict[str, Any],
    ) -> dict[str, Any]:
        evidence = dict(current_profile.get("evidence") or {})
        weak_points = list(evidence.get("weak_points") or [])
        mistake = str(updates.get("mistake_patterns") or "")
        if mistake and mistake not in weak_points:
            weak_points.append(mistake)
        evidence["weak_points"] = weak_points[-12:]
        evolution_records = list(evidence.get("evolution_records") or [])
        evolution_records.append({"trigger": trigger_event, "context": context_data})
        evidence["evolution_records"] = evolution_records[-8:]
        return evidence


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fallback_modality(resource_type: str) -> str:
    if resource_type in {"lecture_doc", "reading"}:
        return "图解和案例优先"
    if resource_type in {"question_bank", "practice_case"}:
        return "讲解先行，再进入练习"
    if resource_type in {"mindmap", "video_script"}:
        return "例题驱动与分步讲解"
    return "图解、案例和短步骤优先"
