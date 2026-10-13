from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel):
    request_id: str
    success: bool
    data: dict | list | str | int | float | None = None
    error: ApiError | None = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ProfileSnapshot(BaseModel):
    id: str
    student_id: str
    knowledge_base_level: str = ""
    cognitive_style: str = ""
    mistake_patterns: str = ""
    modality_preference: str = ""
    pace_preference: str = ""
    motivation_style: str = ""
    evidence: dict = Field(default_factory=dict)
    created_at: datetime


class ProfileChatRequest(BaseModel):
    student_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    major: str | None = None
    goals: str | None = None
    question: str | None = None
    query: str | None = None
    topic: str | None = None


class ProfileChatResult(BaseModel):
    snapshot: ProfileSnapshot
    delta: dict = Field(default_factory=dict)
    rationale: str = ""


class ClarifyRequest(BaseModel):
    student_id: str
    messages: list[ChatMessage]


class ClarifyResult(BaseModel):
    requirement: dict


class GenerateRequest(BaseModel):
    student_id: str
    requirement: dict
    stream: bool = False


class ResourceItem(BaseModel):
    id: str
    student_id: str
    type: str
    title: str
    tags: list[str] = Field(default_factory=list)
    content_uri: str
    meta: dict = Field(default_factory=dict)
    created_at: datetime


class GenerateResult(BaseModel):
    resources: list[ResourceItem]


class PathPlanRequest(BaseModel):
    student_id: str
    goals: str | None = None


class PathPlanResult(BaseModel):
    plan: dict


class PathStageQuestionRequest(BaseModel):
    student_id: str
    stage_id: str | None = None
    knowledge_node_id: str | None = None
    topic: str | None = None
    topic_description: str | None = None
    difficulty: Literal["mixed", "easy", "medium", "hard"] = "mixed"
    count: int = Field(default=10, ge=1, le=50)
    question_types: list[str] = Field(default_factory=lambda: ["single_choice", "multiple_choice", "true_false"])
    type_counts: dict[str, int] = Field(default_factory=dict)


class PathBranchRequest(BaseModel):
    student_id: str
    knowledge_node_id: str
    title: str
    description: str = ""
    mastery: float = Field(default=0, ge=0, le=100)


class PushFeedResult(BaseModel):
    items: list[dict]


class PushFeedbackRequest(BaseModel):
    student_id: str
    resource_id: str
    action: str
    feedback: dict = Field(default_factory=dict)


class PushRemoveRequest(BaseModel):
    student_id: str
    resource_id: str


class TutorAskRequest(BaseModel):
    student_id: str
    question: str = ""
    query: str | None = None
    topic: str | None = None
    context: dict = Field(default_factory=dict)


class TutorAskResult(BaseModel):
    answer: dict


class TutorConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: str | None = None


class TutorSessionRequest(BaseModel):
    student_id: str
    messages: list[TutorConversationMessage]
    started_at: str | None = None
    ended_at: str | None = None
    meta: dict = Field(default_factory=dict)


class EvaluateReportRequest(BaseModel):
    student_id: str


class EvaluateReportResult(BaseModel):
    report: dict


class ExerciseAnswerRequest(BaseModel):
    student_id: str
    question_id: str
    answer: str | list[str]


class ExportPackageRequest(BaseModel):
    student_id: str
    resource_ids: list[str] = Field(default_factory=list)

