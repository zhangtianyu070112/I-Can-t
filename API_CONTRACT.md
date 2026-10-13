# API 契约

统一前缀：`/api`

统一响应结构：

```json
{
  "request_id": "string",
  "success": true,
  "data": {},
  "error": null
}
```

错误响应保留 `success=false` 和 `error.code`、`error.message`。

## 健康检查

- `GET /api/health`

返回后端状态、AI 配置状态、知识库状态和数据目录状态。

## 学习总控

- `GET /api/dashboard/overview?student_id=demo`
- `GET /api/dashboard/activity?student_id=demo&limit=12`

用途：聚合学习者、当前焦点、四类核心指标、八阶段闭环、下一最佳动作、证据时间线和系统状态。

## 用户画像

- `POST /api/profile/chat`
- `POST /api/profile/chat/stream`
- `POST /api/profile/extract`
- `GET /api/profile/current`
- `GET /api/profile/{student_id}/overview`

用途：对话式画像抽取、六维画像更新和流式反馈。

## 资源工坊

- `POST /api/workshop/clarify`
- `POST /api/workshop/generate`
- `POST /api/workshop/create`
- `GET /api/workshop/resources`
- `POST /api/workshop/export`
- `POST /api/agents/generate-resources`
- `GET /api/workshop/overview?student_id=demo`

用途：需求澄清、多智能体资源生成、资源列表和打包导出。

## 知识中枢

- `GET /api/knowledge/map`
- `POST /api/knowledge/search`
- `POST /api/knowledge/ask`
- `GET /api/knowledge/overview`
- `GET /api/knowledge/graph`
- `GET /api/knowledge/mastery`
- `GET /api/knowledge/workspace?student_id=demo`

用途：课程知识图谱、检索、问答、掌握度展示。

## 练习诊断

- `GET /api/exercises`
- `POST /api/exercises/generate`
- `POST /api/exercises/submit`
- `GET /api/exercise/session`
- `POST /api/exercise/answer`
- `GET /api/exercise/stats`
- `GET /api/exercise/wrong-book`

用途：题目加载、答题提交、错题和学习统计。

## 路径推送

- `POST /api/path/plan`
- `POST /api/path/plan/stream`
- `GET /api/path/current`
- `POST /api/recommendations`
- `GET /api/recommendations/current`
- `GET /api/path/overview?student_id=demo`

用途：动态学习路径规划和资源精准推送。

## 智能辅导

- `POST /api/tutor/ask`
- `POST /api/tutor/ask/stream`
- `POST /api/tutor/session`
- `GET /api/tutor/overview?student_id=demo`

用途：结构化答疑、Markdown 输出、知识库边界提示和会话沉淀。

## 多模态实验室

- `GET /api/multimodal/capabilities`
- `POST /api/multimodal/generate`
- `POST /api/multimodal/script`
- `POST /api/multimodal/video-search`
- `POST /api/multimodal/code-case`
- `POST /api/multimodal/voice-lesson`

用途：多模态素材、视频脚本、代码案例、语音辅导方案。

## 评估进化

- `GET /api/evaluation/snapshot`
- `POST /api/evaluation/generate`
- `GET /api/evaluation/evidence`
- `POST /api/evaluation/submit`
- `GET /api/evaluation/report`
- `POST /api/evaluation/evolve`
- `POST /api/evolution/trigger`
- `GET /api/evaluate/overview?student_id=demo`

用途：学习效果评估、证据账本、策略进化和闭环写入。

## 数字人与语音

- `GET /api/avatar/config`
- `GET /api/avatar/sdk-config`
- `POST /api/avatar/session`
- `POST /api/avatar/speak`
- `POST /api/avatar/interrupt`
- `POST /api/avatar/stop`
- `GET /api/voice/realtime/config`
- `POST /api/voice/realtime/sdp`

用途：数字人和实时语音辅导配置。未配置真实服务时返回 disabled 或安全提示。
