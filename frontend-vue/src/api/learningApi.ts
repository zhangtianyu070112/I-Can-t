import { apiGet, apiPost, type ApiResponse } from '@/utils/api'

export type LearningMetric = {
  key: string
  label: string
  value: number
  unit: string
  tone: string
}

export type JourneyItem = {
  key: string
  label: string
  route: string
  status: 'done' | 'next'
  value: number
  evidence: string
}

export type LearningActivity = {
  id: string
  type: string
  title: string
  detail: string
  tone: string
  created_at: string
}

export type DashboardOverview = {
  learner: Record<string, any>
  focus: {
    primary: string
    headline: string
    weak_points: string[]
    keywords: string[]
    recommended_action: string
  }
  metrics: LearningMetric[]
  journey: JourneyItem[]
  next_actions: Array<{ title: string; description: string; route: string; cta: string }>
  activity: LearningActivity[]
  system: Record<string, any>
}

export type ProfileDimension = {
  key: string
  label: string
  value: string
  description: string
  confidence: number
  status: 'ready' | 'pending'
}

export type ProfileOverview = {
  learner: Record<string, any>
  completeness: number
  dimensions: ProfileDimension[]
  focus: { weak_points: string[]; keywords: string[]; headline: string }
  history: Array<{ id: string; version: string; created_at: string; reason: string }>
  comparison?: {
    previous_dimensions?: Record<string, number>
    changes?: Array<{ key: string; label: string; before: string; after: string }>
  }
  evidence_count: number
  snapshot: Record<string, any>
}

export type ResourceSummary = {
  id: string
  type: string
  type_label: string
  title: string
  tags: string[]
  created_at: string
  preview_url: string
  content_uri?: string
  course?: string
  chapter?: string
  agent?: string
  content?: string
  summary?: string
  agent_trace?: any[]
}

export type WorkshopOverview = {
  total: number
  type_count: number
  distribution: Array<{ type: string; label: string; count: number }>
  latest: ResourceSummary[]
  quality: { status: string; risk_score: number; summary: string }
  agents: Array<{ key: string; label: string; role: string }>
}

export type PathOverview = {
  has_plan: boolean
  title: string
  updated_at: string
  stage_count: number
  current_stage: Record<string, any>
  nodes: any[]
  branches?: any[]
  recommendations: ResourceSummary[]
  rules: string[]
  strategy?: string[]
  rationale?: string
  progress?: { pass_threshold: number; current_stage_id: string; updated_at: string }
}

export type PathStageQuestionConfig = {
  stageId?: string
  knowledgeNodeId?: string
  topic?: string
  topicDescription?: string
  difficulty: 'mixed' | 'easy' | 'medium' | 'hard'
  count: number
  questionTypes: string[]
  typeCounts: Record<string, number>
}

export type TutorOverview = {
  session_count: number
  recent_questions: string[]
  suggested_questions: string[]
  capabilities: string[]
  boundary: string
}

export type EvaluationOverview = {
  score: number
  mastery: number
  accuracy: number
  engagement: number
  weak_points: string[]
  evidence: Record<string, number>
  dimensions: Array<{ label: string; value: number }>
  suggestions: Array<{ title: string; detail: string; route: string }>
  timeline: LearningActivity[]
  latest_report?: Record<string, any> | null
  confidence?: { level: string; label: string; evidence_total: number }
}

function dataOrThrow<T>(response: ApiResponse<T>, fallbackMessage: string): T {
  if (!response?.success) {
    throw new Error(response?.error?.message || fallbackMessage)
  }
  return response.data
}

export async function getDashboardOverview(studentId: string): Promise<DashboardOverview> {
  return dataOrThrow(
    await apiGet<DashboardOverview>(`/api/dashboard/overview?student_id=${encodeURIComponent(studentId)}`),
    '学习总控数据加载失败',
  )
}

export async function getProfileOverview(studentId: string): Promise<ProfileOverview> {
  return dataOrThrow(
    await apiGet<ProfileOverview>(`/api/profile/${encodeURIComponent(studentId)}/overview`),
    '画像数据加载失败',
  )
}

export async function updateProfile(payload: {
  student_id: string
  messages: Array<{ role: 'user' | 'assistant'; content: string }>
  major?: string
  goals?: string
}): Promise<any> {
  return dataOrThrow(await apiPost<any>('/api/profile/chat', payload), '画像更新失败')
}

export async function getWorkshopOverview(studentId: string): Promise<WorkshopOverview> {
  return dataOrThrow(
    await apiGet<WorkshopOverview>(`/api/workshop/overview?student_id=${encodeURIComponent(studentId)}`),
    '资源工坊数据加载失败',
  )
}

export async function generateResourcePack(payload: Record<string, any>): Promise<ResourceSummary[]> {
  const data = dataOrThrow<any>(
    await apiPost<any>('/api/agents/generate-resources', payload),
    '资源生成失败',
  )
  return Array.isArray(data?.resources) ? data.resources : []
}

export type ResourceGenerationEvent = {
  type: 'start' | 'agent_start' | 'agent_chunk' | 'agent_done' | 'done' | string
  agent?: string
  title?: string
  text?: string
  index?: number
  agents?: string[]
  resource?: ResourceSummary
}

export async function generateResourcePackStream(
  payload: Record<string, any>,
  onEvent: (event: ResourceGenerationEvent) => void,
): Promise<ResourceSummary[]> {
  const response = await fetch('/api/workshop/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({
      student_id: payload.student_id,
      requirement: payload.requirement || {},
      stream: true,
    }),
  })
  if (!response.ok || !response.body) {
    throw new Error(`资源生成请求失败：HTTP ${response.status}`)
  }

  const resources: ResourceSummary[] = []
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const packets = buffer.split('\n\n')
    buffer = packets.pop() || ''
    for (const packet of packets) {
      const dataLine = packet.split('\n').find((line) => line.startsWith('data: '))
      if (!dataLine) continue
      const envelope = JSON.parse(dataLine.slice(6))
      if (envelope.error) throw new Error(String(envelope.error))
      const event = envelope.event as ResourceGenerationEvent | undefined
      if (!event) continue
      if (event.type === 'agent_done' && event.resource) resources.push(event.resource)
      onEvent(event)
    }
  }

  return resources
}

export async function exportResourcePackage(studentId: string, resourceIds: string[]): Promise<string> {
  const data = dataOrThrow<any>(
    await apiPost<any>('/api/export/package', { student_id: studentId, resource_ids: resourceIds }),
    '资源包导出失败',
  )
  return data?.download_url || data?.url || ''
}

export async function getKnowledgeWorkspace(studentId: string): Promise<any> {
  return dataOrThrow(
    await apiGet<any>(`/api/knowledge/workspace?student_id=${encodeURIComponent(studentId)}`),
    '知识中枢数据加载失败',
  )
}

export async function getKnowledgeGraph(
  studentId: string,
  options: { course?: string; sourceType?: string; keyword?: string; maxNodes?: number } = {},
): Promise<any> {
  const params = new URLSearchParams({
    student_id: studentId,
    course: options.course || '',
    source_type: options.sourceType || 'all',
    keyword: options.keyword || '',
    max_nodes: String(options.maxNodes || 56),
  })
  return dataOrThrow(await apiGet<any>(`/api/knowledge/graph?${params}`), '知识图谱加载失败')
}

export async function searchKnowledge(studentId: string, query: string): Promise<any[]> {
  const data = dataOrThrow<any>(
    await apiGet<any>(`/api/knowledge/search?student_id=${encodeURIComponent(studentId)}&q=${encodeURIComponent(query)}&limit=8`),
    '知识检索失败',
  )
  return data?.results || []
}

export async function trackKnowledgeNode(studentId: string, nodeId: string, score: number): Promise<any> {
  return dataOrThrow(
    await apiPost<any>('/api/knowledge/track', { student_id: studentId, node_id: nodeId, score, note: '知识中枢学习记录' }),
    '节点学习记录失败',
  )
}

export async function getPathOverview(studentId: string): Promise<PathOverview> {
  return dataOrThrow(
    await apiGet<PathOverview>(`/api/path/overview?student_id=${encodeURIComponent(studentId)}`),
    '学习路径加载失败',
  )
}

export async function planLearningPath(studentId: string, goals: string): Promise<any> {
  return dataOrThrow(
    await apiPost<any>('/api/path/plan', { student_id: studentId, goals }),
    '学习路径生成失败',
  )
}

export async function addKnowledgeBranchToPath(
  studentId: string,
  node: { id: string; title: string; description?: string; mastery?: number },
): Promise<any> {
  return dataOrThrow(
    await apiPost<any>('/api/path/branch', {
      student_id: studentId,
      knowledge_node_id: node.id,
      title: node.title,
      description: node.description || '',
      mastery: node.mastery || 0,
    }),
    '知识分支加入路径失败',
  )
}

export async function generatePathStageQuestions(
  studentId: string,
  config: PathStageQuestionConfig,
): Promise<any> {
  return dataOrThrow(
    await apiPost<any>('/api/path/stage/questions', {
      student_id: studentId,
      stage_id: config.stageId || null,
      knowledge_node_id: config.knowledgeNodeId || null,
      topic: config.topic || null,
      topic_description: config.topicDescription || null,
      difficulty: config.difficulty,
      count: config.count,
      question_types: config.questionTypes,
      type_counts: config.typeCounts,
    }),
    '阶段题库生成失败',
  )
}

export async function getPushFeed(studentId: string): Promise<any[]> {
  const data = dataOrThrow<any>(
    await apiGet<any>(`/api/push/feed?student_id=${encodeURIComponent(studentId)}`),
    '资源推荐加载失败',
  )
  return data?.items || []
}

export async function sendResourceFeedback(studentId: string, resourceId: string, action: string): Promise<any> {
  return dataOrThrow(
    await apiPost<any>('/api/push/feedback', { student_id: studentId, resource_id: resourceId, action, feedback: {} }),
    '反馈提交失败',
  )
}

export async function removePushedResource(studentId: string, resourceId: string): Promise<any> {
  return dataOrThrow(
    await apiPost<any>('/api/push/remove', { student_id: studentId, resource_id: resourceId }),
    '推送资源删除失败',
  )
}

export async function getTutorOverview(studentId: string): Promise<TutorOverview> {
  return dataOrThrow(
    await apiGet<TutorOverview>(`/api/tutor/overview?student_id=${encodeURIComponent(studentId)}`),
    '辅导上下文加载失败',
  )
}

export async function askTutor(studentId: string, question: string, context: Record<string, any> = {}): Promise<any> {
  return dataOrThrow(
    await apiPost<any>('/api/tutor/ask', { student_id: studentId, question, context }),
    '智能辅导回答失败',
  )
}

export async function saveTutorSession(studentId: string, messages: any[]): Promise<any> {
  return dataOrThrow(
    await apiPost<any>('/api/tutor/session', { student_id: studentId, messages }),
    '辅导会话保存失败',
  )
}

export async function getEvaluationOverview(studentId: string): Promise<EvaluationOverview> {
  return dataOrThrow(
    await apiGet<EvaluationOverview>(`/api/evaluate/overview?student_id=${encodeURIComponent(studentId)}`),
    '评估证据加载失败',
  )
}

export async function generateEvaluation(studentId: string): Promise<any> {
  return dataOrThrow(
    await apiPost<any>('/api/evaluate/report', { student_id: studentId }),
    '学习评估生成失败',
  )
}

export async function evolveLearningStrategy(studentId: string, context: Record<string, any>): Promise<any> {
  return dataOrThrow(
    await apiPost<any>('/api/evolution/trigger', {
      student_id: studentId,
      trigger_event: 'manual_evaluation_review',
      context_data: context,
    }),
    '策略进化失败',
  )
}
