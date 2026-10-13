from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.streaming import stream_live_operation, stream_response
from app.agents import Orchestrator
from app.core.ids import new_id
from app.evolution import EvolutionEngine
from app.repo import insert_learning_event
from app.schemas import ApiResponse, TutorAskRequest, TutorSessionRequest
from app.services.learning_state import tutor_overview


router = APIRouter(prefix="/api/tutor", tags=["tutor"])
orchestrator = Orchestrator()
MIN_KNOWLEDGE_REFERENCE_SCORE = 0.2


@router.get("/overview", response_model=ApiResponse)
async def overview(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(request_id=request_id, success=True, data=tutor_overview(student_id))
    except Exception as e:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "TUTOR_OVERVIEW_ERROR", "message": str(e)},
        )
evolution_engine = EvolutionEngine()


@router.post("/ask", response_model=ApiResponse)
async def ask(req: TutorAskRequest) -> ApiResponse:
    request_id = new_id()
    try:
        result = await _run_tutor(req)
        return ApiResponse(request_id=request_id, success=True, data=_with_legacy_tutor_fields(result))
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "TUTOR_ERROR", "message": str(e)})


@router.post("/ask/stream")
async def ask_stream(req: TutorAskRequest):
    request_id = new_id()

    async def work(on_chunk):
        result = await _run_tutor(req, on_chunk=on_chunk)
        return _with_legacy_tutor_fields(result)

    def text(result: dict) -> str:
        answer = result.get("answer", result)
        if isinstance(answer, str):
            return answer
        if isinstance(answer, dict):
            for key in ("answer", "text", "summary", "content", "explanation"):
                if answer.get(key):
                    return str(answer[key])
        return str(answer)

    return stream_response(
        stream_live_operation(
            request_id=request_id,
            work=work,
            start_message="开始生成智能辅导回答",
            final_key="result",
            fallback_text=text,
            chunk_path="answer",
        )
    )


async def _run_tutor(req: TutorAskRequest, on_chunk=None) -> dict:
    """Normalize every accepted question alias before entering the formal orchestrator."""
    return await orchestrator.tutor_ask(
        student_id=req.student_id,
        question=_normalize_tutor_question(req),
        context=req.context,
        on_chunk=on_chunk,
    )


def _normalize_tutor_question(req: TutorAskRequest) -> str:
    for value in (req.question, req.query, req.topic):
        normalized = " ".join(str(value or "").split())
        if normalized:
            return normalized
    return ""


def _with_legacy_tutor_fields(result: dict) -> dict:
    """Keep the formal answer untouched while exposing the legacy flat contract."""
    payload = dict(result) if isinstance(result, dict) else {"answer": result}
    answer = payload.get("answer", result)
    references = _answer_references(answer, payload)
    credible_references = _credible_references(references)
    markdown = _answer_markdown(answer)
    if not credible_references:
        markdown = _append_evidence_notice(markdown)

    return {
        **payload,
        "answer": answer,
        "markdown": markdown,
        "steps": _answer_steps(answer, markdown),
        "confidence": _answer_confidence(answer, credible_references),
        "knowledge_base_hit": bool(credible_references),
    }


def _answer_references(answer, payload: dict) -> list:
    candidates = answer.get("references") if isinstance(answer, dict) else None
    if not isinstance(candidates, list):
        candidates = payload.get("references")
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if item]


def _credible_references(references: list) -> list:
    credible = []
    for reference in references:
        if not isinstance(reference, dict):
            continue
        if reference.get("verified") is True:
            credible.append(reference)
            continue
        score = _normalized_confidence(reference.get("score"))
        if score is not None and score >= MIN_KNOWLEDGE_REFERENCE_SCORE:
            credible.append(reference)
    return credible


def _answer_markdown(answer) -> str:
    if isinstance(answer, str):
        return answer.strip()
    if isinstance(answer, dict):
        for key in ("markdown", "text", "answer", "content", "summary", "explanation"):
            value = answer.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _append_evidence_notice(markdown: str) -> str:
    notice = "当前课程知识库证据不足，未检索到可引用证据；以上内容仅作答疑框架，关键结论需要补充课程资料后核验。"
    if notice in markdown:
        return markdown
    return f"{markdown}\n\n> {notice}".strip()


def _answer_steps(answer, markdown: str) -> list[str]:
    if isinstance(answer, dict) and isinstance(answer.get("steps"), list):
        steps = [str(item).strip() for item in answer["steps"] if str(item).strip()]
        if steps:
            return steps

    import re

    steps: list[str] = []
    marker = re.compile(r"^\s*(?:\d+[.)、]|[-*])\s*(.+?)\s*$")
    for line in markdown.splitlines():
        match = marker.match(line)
        if match and match.group(1):
            steps.append(match.group(1))
    return steps


def _answer_confidence(answer, references: list) -> float | None:
    if not references:
        return None

    if isinstance(answer, dict):
        confidence = _normalized_confidence(answer.get("confidence"))
        if confidence is not None:
            return confidence

    scores = [
        score
        for reference in references
        if isinstance(reference, dict)
        for score in [_normalized_confidence(reference.get("score"))]
        if score is not None
    ]
    return max(scores) if scores else None


def _normalized_confidence(value) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= score <= 1:
        return round(score, 4)
    if 1 < score <= 100:
        return round(score / 100, 4)
    return None


@router.post("/session", response_model=ApiResponse)
async def save_session(req: TutorSessionRequest) -> ApiResponse:
    request_id = new_id()
    try:
        messages = [m.model_dump() for m in req.messages if m.content.strip()]
        analysis = _analyze_session(messages)
        session_payload = {
            "messages": messages,
            "started_at": req.started_at,
            "ended_at": req.ended_at,
            "meta": req.meta,
            "analysis": analysis,
        }
        insert_learning_event(req.student_id, "tutor_session", session_payload)

        for question in analysis["questions"]:
            insert_learning_event(
                req.student_id,
                "tutor",
                {
                    "question": question[:160],
                    "source": "realtime_session",
                    "weak_points": analysis["weak_points"],
                },
            )

        evolution = None
        if analysis["weak_points"] or len(analysis["questions"]) >= 2:
            evolution = await evolution_engine.evaluate_and_evolve(
                student_id=req.student_id,
                trigger_event="repeated_tutor_question",
                context_data={
                    "topic": "；".join(analysis["weak_points"][:4] or analysis["questions"][:3]),
                    "questions": analysis["questions"][:6],
                    "weak_points": analysis["weak_points"],
                    "session_message_count": len(messages),
                    "started_at": req.started_at,
                    "ended_at": req.ended_at,
                },
            )

        return ApiResponse(
            request_id=request_id,
            success=True,
            data={
                "saved": True,
                "message_count": len(messages),
                "analysis": analysis,
                "evolution": evolution,
            },
        )
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "TUTOR_SESSION_ERROR", "message": str(e)})


def _analyze_session(messages: list[dict]) -> dict:
    user_messages = [
        str(m.get("content", "")).strip()
        for m in messages
        if m.get("role") == "user" and str(m.get("content", "")).strip()
    ]
    assistant_messages = [
        str(m.get("content", "")).strip()
        for m in messages
        if m.get("role") == "assistant" and str(m.get("content", "")).strip()
    ]
    questions = [_clean_text(text) for text in user_messages if _clean_text(text)]
    weak_points = _extract_weak_points_from_questions(questions)
    repeated_topics = _repeated_terms(" ".join(questions))
    summary_parts = []
    if questions:
        summary_parts.append(f"本次实时辅导学生共提出 {len(questions)} 个问题")
    if weak_points:
        summary_parts.append("暴露的薄弱点集中在：" + "、".join(weak_points[:5]))
    elif repeated_topics:
        summary_parts.append("高频关注主题包括：" + "、".join(repeated_topics[:5]))
    else:
        summary_parts.append("本次对话已保存，后续可结合更多练习和反馈继续分析。")
    return {
        "questions": questions,
        "assistant_reply_count": len(assistant_messages),
        "weak_points": weak_points,
        "repeated_topics": repeated_topics,
        "summary": "；".join(summary_parts),
    }


def _clean_text(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())[:500]


def _extract_weak_points_from_questions(questions: list[str]) -> list[str]:
    markers = [
        "不懂",
        "不会",
        "不理解",
        "没听懂",
        "搞不清",
        "混淆",
        "容易错",
        "为什么",
        "怎么判断",
        "怎么区分",
        "区别",
        "步骤",
        "原理",
    ]
    weak: list[str] = []
    for question in questions:
        for marker in markers:
            if marker in question:
                weak.append(_clip_focus(question, marker))
                break
    weak.extend(_repeated_terms(" ".join(questions)))
    deduped: list[str] = []
    for item in weak:
        item = item.strip(" ，。？！；:：")
        if item and item not in deduped:
            deduped.append(item)
    return deduped[:8]


def _clip_focus(text: str, marker: str) -> str:
    idx = text.find(marker)
    start = max(0, idx - 18)
    end = min(len(text), idx + len(marker) + 34)
    return text[start:end]


def _repeated_terms(text: str) -> list[str]:
    import re
    from collections import Counter

    stop_words = {"这个", "那个", "老师", "一下", "还是", "是不是", "为什么", "怎么", "可以", "如果", "就是", "然后"}
    terms = re.findall(r"[A-Za-z][A-Za-z0-9_+-]{2,}|[\u4e00-\u9fff]{2,8}", text)
    counts = Counter(t for t in terms if t not in stop_words)
    return [term for term, count in counts.most_common(8) if count >= 2]
