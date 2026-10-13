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


def flow_a_full_learning_loop():
    student_id = PROFILE["student_id"]

    profile = assert_success(
        post(
            "/api/profile/chat",
            {
                "student_id": student_id,
                "messages": [{"role": "user", "content": INPUTS["profile_input"]}],
                "major": PROFILE["major"],
                "goals": PROFILE["learning_goal"],
            },
        ),
        "flow profile",
    )
    assert_true(profile.get("snapshot"), "profile snapshot missing")

    resources = assert_success(post("/api/agents/generate-resources", RESOURCE_REQUEST), "flow resources")
    resource_items = resources.get("resources") or []
    assert_true(resource_items, "flow resources empty")

    path = assert_success(post("/api/path/plan", {"student_id": student_id, "goals": PROFILE["learning_goal"]}), "flow path")
    path_nodes = (path.get("path") or {}).get("nodes") or []
    assert_true(path_nodes, "flow path empty")

    recommendations = assert_success(post("/api/recommendations", {"student_id": student_id}), "flow recommendations")
    assert_true(recommendations.get("items") or recommendations.get("recommendations"), "flow recommendations empty")

    tutor = assert_success(post("/api/tutor/ask", {"student_id": student_id, "question": INPUTS["tutor_question"]}), "flow tutor")
    assert_true(tutor.get("markdown"), "flow tutor answer empty")

    generated = assert_success(post("/api/exercises/generate", {"student_id": student_id}), "flow exercises")
    first = (generated.get("questions") or [])[0]
    diagnosis = assert_success(
        post("/api/exercises/submit", {"student_id": student_id, "question_id": first["id"], "answer": "B"}),
        "flow exercise submit",
    )
    assert_true(diagnosis.get("analysis"), "flow diagnosis missing")

    evaluation = assert_success(post("/api/evaluation/submit", {"student_id": student_id}), "flow evaluation")
    assert_true(evaluation.get("suggestions"), "flow evaluation suggestions missing")

    evolved = assert_success(post("/api/evaluation/evolve", {"student_id": student_id}), "flow evolve")
    assert_true(evolved.get("rules"), "flow evolve rules missing")


def flow_b_knowledge_boundary():
    student_id = PROFILE["student_id"]
    inside = assert_success(
        post("/api/knowledge/ask", {"student_id": student_id, "question": "单链表插入操作是什么？"}),
        "knowledge inside",
    )
    assert_true(inside.get("answer"), "inside knowledge answer missing")
    outside = assert_success(
        post("/api/knowledge/ask", {"student_id": student_id, "question": INPUTS["out_of_scope_question"]}),
        "knowledge outside",
    )
    answer = outside.get("answer") or {}
    assert_true("不足" in answer.get("markdown", ""), "outside knowledge should state limitation")


def flow_c_demo_mode_without_ai_key():
    health = assert_success(get("/api/health"), "demo health")
    assert_true((health.get("ai_provider") or {}).get("demo_mode") is True, "demo mode flag missing")
    resources = assert_success(post("/api/agents/generate-resources", RESOURCE_REQUEST), "demo resources")
    assert_true(len(resources.get("resources") or []) >= 5, "demo resources should be available without AI key")
    tutor = assert_success(
        post("/api/tutor/ask", {"student_id": PROFILE["student_id"], "question": INPUTS["out_of_scope_question"]}),
        "demo tutor boundary",
    )
    assert_true(tutor.get("knowledge_base_hit") is False, "demo tutor boundary should not hallucinate")


def main() -> int:
    results: list[dict] = []
    for case in (flow_a_full_learning_loop, flow_b_knowledge_boundary, flow_c_demo_mode_without_ai_key):
        run_case(results, case.__name__, case)
    record_result("integration_flow.json", results)
    return 1 if any(item["status"] != "passed" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
