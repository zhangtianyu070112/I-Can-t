from __future__ import annotations

from fastapi import APIRouter

from app.core.ids import new_id
from app.schemas import ApiResponse


router = APIRouter(prefix="/api/integration", tags=["integration"])


@router.get("/teammate-catalog", response_model=ApiResponse)
async def teammate_catalog() -> ApiResponse:
    """Expose how teammate work is absorbed into the current FastAPI + Vue stack."""

    capabilities = [
        {
            "key": "multi_agent_orchestration",
            "name": "多智能体资源编排",
            "from_teammate": "backend/agents/coordinator.py",
            "current_module": "backend/app/agents/orchestrator.py",
            "entry": "/workshop",
            "status": "已融合",
            "value": "沿用当前 Orchestrator，把讲解文档、思维导图、题库、拓展阅读、代码案例、视频脚本统一沉淀为学习资源。",
        },
        {
            "key": "exam_generation",
            "name": "试卷与题库生成",
            "from_teammate": "frontend/src/components/ExamGenerator.vue + backend/exam",
            "current_module": "backend/app/services/exercise_bank.py",
            "entry": "/exercise",
            "status": "已吸收为练习诊断",
            "value": "优先读取资源工坊生成的 question_bank，形成可答题、可统计、可反哺画像的闭环。",
        },
        {
            "key": "ppt_outline",
            "name": "PPT/展示大纲生成",
            "from_teammate": "frontend/src/components/PptGenerator.vue",
            "current_module": "frontend-vue/src/pages/WorkshopPage.vue",
            "entry": "/workshop",
            "status": "作为资源类型规划",
            "value": "保留可编辑大纲、课堂展示、答辩素材的设计思路，后续可作为 presentation_resource 扩展到资源工坊。",
        },
        {
            "key": "knowledge_games",
            "name": "知识游戏化练习",
            "from_teammate": "frontend/src/components/KnowledgeGames.vue",
            "current_module": "frontend-vue/src/pages/ExercisePage.vue",
            "entry": "/exercise",
            "status": "作为互动练习方案",
            "value": "把游戏化得分、闯关、分类、配对等交互思路收敛为练习诊断的可扩展展示方式。",
        },
        {
            "key": "voice_agent",
            "name": "语音/视频辅导",
            "from_teammate": "frontend/src/components/VoiceAgent.vue + RealtimeVideoCall.vue",
            "current_module": "backend/app/api/routers/multimodal.py",
            "entry": "/multimodal",
            "status": "已融合",
            "value": "当前系统生成语音辅导脚本、ASR/TTS 配置清单和失败兜底方案，可沉淀为可推送资源。",
        },
        {
            "key": "code_case",
            "name": "代码实操案例",
            "from_teammate": "backend/agents/code_agent.py + CodeGenerator.vue",
            "current_module": "backend/app/api/routers/multimodal.py",
            "entry": "/multimodal",
            "status": "已融合",
            "value": "按主题和语言生成可复现代码任务、运行步骤、验收标准和扩展挑战。",
        },
        {
            "key": "video_resource",
            "name": "教学视频资源",
            "from_teammate": "backend/agents/video_agent.py + VideoGenerator.vue",
            "current_module": "backend/app/api/routers/multimodal.py",
            "entry": "/multimodal",
            "status": "已融合",
            "value": "生成国内平台检索词、观看顺序和学习建议，避免伪造不可访问的视频链接。",
        },
        {
            "key": "mindmap_visual",
            "name": "思维导图结构化预览",
            "from_teammate": "backend/agents/mindmap_agent.py",
            "current_module": "backend/app/services/resource_structure.py",
            "entry": "/workshop",
            "status": "已融合",
            "value": "解析 Mermaid mindmap 为前端可预览结构，支持讲解时展示知识层级。",
        },
    ]

    return ApiResponse(
        request_id=new_id(),
        success=True,
        data={
            "source_folder": "项目源码（当前提交包）",
            "strategy": "保持当前 FastAPI + Vue 3 主框架，不迁移独立 Java 后端、另一套前端运行时、node_modules、.env 或数据库配置。",
            "capabilities": capabilities,
            "supporting_mechanisms": [
                {
                    "key": "learning_trace",
                    "name": "学习事件追踪与数据闭环",
                    "from_teammate": "新成果/软件杯/frontend-vue/src/pages/DataLogPage.vue",
                    "current_module": "backend/app/services/knowledge_hub.py + backend/app/repo.py",
                    "entry": "GET /api/knowledge/overview -> data.activity",
                    "status": "已转为后端闭环机制",
                    "value": "不作为独立前端功能展示，而是记录画像更新、资源生成、路径规划、推送反馈、智能辅导和评估事件，供首页、知识中枢、路径推送和评估进化读取。",
                },
            ],
            "not_imported": [
                {
                    "name": "backend-java",
                    "reason": "当前主工程已统一为 FastAPI 后端；直接并入 Spring Boot/MySQL 会增加演示部署复杂度。",
                },
                {
                    "name": "队友独立 frontend 运行时",
                    "reason": "只吸收交互模式和功能设计，不覆盖当前 Vue 3 页面结构和路由。",
                },
                {
                    "name": ".env / 快速启动脚本",
                    "reason": "避免覆盖当前项目的大模型、数据库和启动配置。",
                },
            ],
        },
    )
