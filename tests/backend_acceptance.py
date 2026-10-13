from __future__ import annotations

import sys

from testlib import assert_success, assert_true, load_fixture, record_result, request_json, run_case


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PROFILE = load_fixture("student_profile.json")
INPUTS = load_fixture("sample_inputs.json")
RESOURCE_REQUEST = load_fixture("resource_request.json")


def post(path: str, payload: dict):
    return request_json(BASE_URL, "POST", path, payload)


def get(path: str):
    return request_json(BASE_URL, "GET", path)


def test_health():
    data = assert_success(get("/api/health"), "health")
    assert_true("backend" in data, "health.data.backend missing")
    assert_true("ai_provider" in data, "health.data.ai_provider missing")
    assert_true("knowledge_base" in data, "health.data.knowledge_base missing")


def test_learning_dashboard_unifies_evidence():
    data = assert_success(get(f"/api/dashboard/overview?student_id={PROFILE['student_id']}"), "dashboard overview")
    assert_true(data.get("learner"), "dashboard learner missing")
    assert_true(data.get("focus"), "dashboard focus missing")
    assert_true(len(data.get("journey") or []) >= 7, "dashboard journey incomplete")
    assert_true(len(data.get("metrics") or []) >= 4, "dashboard metrics incomplete")
    assert_true(data.get("next_actions"), "dashboard next actions missing")


def test_profile_chat_extracts_six_dimensions():
    payload = {
        "student_id": PROFILE["student_id"],
        "messages": [{"role": "user", "content": INPUTS["profile_input"]}],
        "major": PROFILE["major"],
        "goals": PROFILE["learning_goal"],
    }
    data = assert_success(post("/api/profile/chat", payload), "profile chat")
    snapshot = data.get("snapshot") or {}
    dimensions = snapshot.get("dimensions") or {}
    assert_true(len(dimensions) >= 6, f"profile dimensions < 6: {dimensions}")
    assert_true(snapshot.get("student_id") == PROFILE["student_id"], "profile student_id mismatch")


def test_profile_empty_input_no_500():
    data = assert_success(post("/api/profile/extract", {"student_id": PROFILE["student_id"], "question": ""}), "profile empty")
    assert_true(len((data.get("dimensions") or {})) >= 6, "empty profile fallback dimensions missing")


def test_generate_resources_has_required_fields():
    data = assert_success(post("/api/agents/generate-resources", RESOURCE_REQUEST), "generate resources")
    resources = data.get("resources") or []
    assert_true(len(resources) >= 5, f"expected >=5 resources, got {len(resources)}")
    required = {"id", "type", "title", "summary", "content", "tags", "difficulty", "estimated_minutes", "agent_trace"}
    for item in resources[:5]:
        missing = required - set(item)
        assert_true(not missing, f"resource missing fields {missing}: {item}")
        assert_true(len(item.get("agent_trace") or []) >= 3, "agent_trace must include multiple agents")


def test_path_plan_shape():
    data = assert_success(
        post("/api/path/plan", {"student_id": PROFILE["student_id"], "goals": PROFILE["learning_goal"]}),
        "path plan",
    )
    nodes = (data.get("path") or {}).get("nodes") or []
    assert_true(len(nodes) >= 5, "path.nodes is empty or too short")
    required = {"step", "title", "goal", "resources", "tasks", "checkpoint", "status"}
    assert_true(all(required <= set(node) for node in nodes), "path node missing required fields")


def test_recommendations_related_to_weakness():
    data = assert_success(post("/api/recommendations", {"student_id": PROFILE["student_id"]}), "recommendations")
    recommendations = data.get("recommendations") or data.get("items") or []
    assert_true(recommendations, "recommendations empty")
    assert_true(all(item.get("reason") for item in recommendations), "recommendation reason missing")


def test_tutor_markdown_and_boundary():
    data = assert_success(
        post("/api/tutor/ask", {"student_id": PROFILE["student_id"], "question": INPUTS["tutor_question"]}),
        "tutor ask",
    )
    assert_true(data.get("markdown"), "tutor markdown missing")
    assert_true(data.get("steps"), "tutor steps missing")
    assert_true("confidence" in data, "tutor confidence missing")

    boundary = assert_success(
        post("/api/tutor/ask", {"student_id": PROFILE["student_id"], "question": INPUTS["out_of_scope_question"]}),
        "tutor boundary",
    )
    assert_true(boundary.get("knowledge_base_hit") is False, "out-of-scope question should not hit knowledge base")
    assert_true("不足" in boundary.get("markdown", ""), "out-of-scope answer should state knowledge base limitation")


def test_evaluation_submit():
    data = assert_success(post("/api/evaluation/submit", {"student_id": PROFILE["student_id"]}), "evaluation submit")
    for key in ("score", "mastery", "weaknesses", "suggestions"):
        assert_true(key in data, f"evaluation missing {key}")


def test_exercises_generate_and_submit():
    generated = assert_success(post("/api/exercises/generate", {"student_id": PROFILE["student_id"]}), "exercises generate")
    questions = generated.get("questions") or []
    assert_true(questions, "questions empty")
    assert_true(len({q.get("type") for q in questions}) >= 2, "need at least two question types")
    first = questions[0]
    submitted = assert_success(
        post("/api/exercises/submit", {"student_id": PROFILE["student_id"], "question_id": first["id"], "answer": ""}),
        "exercises submit empty answer",
    )
    for key in ("correct", "analysis", "knowledge_point", "error_reason", "suggestion"):
        assert_true(key in submitted, f"exercise submit missing {key}")


def test_knowledge_and_multimodal():
    kb = assert_success(post("/api/knowledge/ask", {"student_id": PROFILE["student_id"], "question": "单链表插入操作是什么？"}), "knowledge ask")
    assert_true(kb.get("answer"), "knowledge answer missing")
    graph = assert_success(get(f"/api/knowledge/map?student_id={PROFILE['student_id']}&max_nodes=40"), "knowledge map")
    assert_true("nodes" in graph and "edges" in graph, "knowledge graph nodes/edges missing")

    mm = assert_success(
        post("/api/multimodal/generate", {"student_id": PROFILE["student_id"], "topic": INPUTS["multimodal_request"]}),
        "multimodal generate",
    )
    assert_true(mm.get("status") == "completed", "multimodal status missing")
    assert_true(mm.get("animation_script") or mm.get("video_script") or mm.get("diagram"), "multimodal content missing")


def test_workshop_export():
    assert_success(post("/api/workshop/create", RESOURCE_REQUEST), "workshop create")
    data = assert_success(get(f"/api/workshop/resources?student_id={PROFILE['student_id']}"), "workshop resources")
    assert_true("resources" in data, "workshop resources missing")
    export_data = assert_success(post("/api/workshop/export", {"student_id": PROFILE["student_id"]}), "workshop export")
    assert_true(export_data.get("status") in {"ready", "completed"}, "export status invalid")


def main() -> int:
    results: list[dict] = []
    cases = [
        test_health,
        test_learning_dashboard_unifies_evidence,
        test_profile_chat_extracts_six_dimensions,
        test_profile_empty_input_no_500,
        test_generate_resources_has_required_fields,
        test_path_plan_shape,
        test_recommendations_related_to_weakness,
        test_tutor_markdown_and_boundary,
        test_evaluation_submit,
        test_exercises_generate_and_submit,
        test_knowledge_and_multimodal,
        test_workshop_export,
    ]
    for case in cases:
        run_case(results, case.__name__, case)
    record_result("backend_acceptance.json", results)
    failed = [item for item in results if item["status"] != "passed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
