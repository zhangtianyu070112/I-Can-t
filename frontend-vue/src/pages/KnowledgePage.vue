<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch, type Component } from 'vue'
import { useRouter } from 'vue-router'
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  Boxes,
  BrainCircuit,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  ClipboardList,
  Compass,
  Cpu,
  Database,
  FileText,
  Filter,
  Fullscreen,
  GitBranch,
  GraduationCap,
  HardDrive,
  Layers3,
  LoaderCircle,
  MemoryStick,
  Minimize2,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Power,
  RefreshCw,
  Route,
  Search,
  Settings2,
  Sparkles,
  Target,
  Terminal,
  Upload,
  Workflow,
  X,
} from 'lucide-vue-next'
import {
  addKnowledgeBranchToPath,
  generatePathStageQuestions,
  getKnowledgeGraph,
  getKnowledgeWorkspace,
  getPathOverview,
  searchKnowledge,
} from '@/api/learningApi'
import { useStudent } from '@/composables/useStudent'

type NodeKind = 'course' | 'chapter' | 'concept' | 'resource'
type MasteryFilter = 'all' | 'mastered' | 'weak' | 'unlearned' | 'priority'
type RelationGroup = 'hierarchy' | 'prerequisite' | 'resource'

type KnowledgeCourse = {
  id: string
  title: string
  source_type?: string
  chapter_count?: number
  concept_count?: number
}

type KnowledgeNode = {
  id: string
  name?: string
  title?: string
  desc?: string
  kind?: NodeKind | string
  layer?: string
  category?: string
  mastery?: number
  evidence_count?: number
  relation_count?: number
  source_title?: string
  source_type?: string
  source_path?: string
  chapter?: string
  keywords?: string[]
  status?: string
}

type KnowledgeEdge = {
  source: string
  target: string
  label?: string
  type?: string
}

type KnowledgeGraph = {
  course: string
  selected_course: string
  course_summary?: string
  courses: KnowledgeCourse[]
  nodes: KnowledgeNode[]
  edges: KnowledgeEdge[]
  legend: Array<{ category: string; label: string; color: string }>
  stats: Record<string, number>
}

type SearchResult = {
  id?: string
  title?: string
  name?: string
  source_title?: string
  source?: string
  source_type?: string
  excerpt?: string
  tags?: string[]
  score?: number
  relevance?: number
}

type PositionedNode = {
  node: KnowledgeNode
  x: number
  y: number
  width: number
  height: number
  index: number
}

type PositionedEdge = KnowledgeEdge & {
  d: string
  group: RelationGroup
}

const emptyGraph = (): KnowledgeGraph => ({
  course: '',
  selected_course: '',
  courses: [],
  nodes: [],
  edges: [],
  legend: [],
  stats: {},
})

const router = useRouter()
const { studentId } = useStudent()
const workspace = ref<Record<string, any> | null>(null)
const graph = ref<KnowledgeGraph>(emptyGraph())
const graphLoading = ref(true)
const workspaceLoading = ref(true)
const refreshing = ref(false)
const addingToPath = ref(false)
const generatingExercise = ref(false)
const uploadingTextbook = ref(false)
const textbookInput = ref<HTMLInputElement | null>(null)
const graphError = ref('')
const workspaceError = ref('')
const searchError = ref('')
const selectedNodeId = ref('')
const selectedCourse = ref('')
const sourceType = ref('all')
const levelFilter = ref<'all' | NodeKind>('all')
const masteryFilter = ref<MasteryFilter>('all')
const relationVisibility = ref<Record<RelationGroup, boolean>>({
  hierarchy: true,
  prerequisite: true,
  resource: true,
})
const keyword = ref('')
const searchResults = ref<SearchResult[]>([])
const selectedSearchResult = ref<SearchResult | null>(null)
const searchAttempted = ref(false)
const searching = ref(false)
const focusPath = ref(false)
const filtersCollapsed = ref(false)
const isFullscreen = ref(false)
const mobilePanel = ref<'none' | 'filters' | 'details'>('none')
const notice = ref('')
const graphZoom = ref(1)
const graphInteractionStatus = ref('知识图谱已就绪。')
const fullscreenTrigger = ref<HTMLButtonElement | null>(null)
const knowledgeRoot = ref<HTMLElement | null>(null)
const graphViewport = ref<HTMLElement | null>(null)
const viewportWidth = ref(1080)
let resizeObserver: ResizeObserver | null = null
let noticeTimer: ReturnType<typeof window.setTimeout> | null = null
let fullscreenFallback = false
let previousBodyOverflow = ''
let bodyOverflowLocked = false

const GRAPH_ZOOM_MIN = 0.6
const GRAPH_ZOOM_MAX = 1.8
const GRAPH_ZOOM_STEP = 0.1

const levelOptions: Array<{ value: 'all' | NodeKind; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'chapter', label: '章节' },
  { value: 'concept', label: '知识点' },
  { value: 'resource', label: '资源' },
]

const masteryOptions: Array<{ value: MasteryFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'mastered', label: '已掌握' },
  { value: 'weak', label: '薄弱' },
  { value: 'unlearned', label: '未学习' },
  { value: 'priority', label: '推荐优先' },
]

function nodeName(item: KnowledgeNode | null | undefined) {
  return item?.name || item?.title || '知识节点'
}

function nodeKind(item: KnowledgeNode | null | undefined): NodeKind {
  const kind = String(item?.kind || '')
  return ['course', 'chapter', 'concept', 'resource'].includes(kind) ? kind as NodeKind : 'concept'
}

function nodeTypeLabel(item: KnowledgeNode | null | undefined) {
  return ({
    course: '课程入口',
    chapter: '章节模块',
    concept: '核心知识点',
    resource: '资源 / 题型',
  } as Record<NodeKind, string>)[nodeKind(item)]
}

function sourceLabel(value: string | undefined) {
  return ({
    uploaded_textbook: '上传教材',
    course_material: '课程资料',
    generated_resource: '生成资源',
    generated: '生成资源',
    sample_resource: '示例资源',
    path_output: '路径成果',
    course: '课程资料',
  } as Record<string, string>)[String(value || '')] || value || '课程资料'
}

function masteryValue(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : 0
}

function masteryStatus(item: KnowledgeNode) {
  if (nodeKind(item) === 'course') return 'current'
  if (nodeKind(item) === 'resource') return 'recommended'
  const score = masteryValue(item.mastery)
  if (score >= 80) return 'mastered'
  if (score <= 0) return 'unlearned'
  if (score < 60) return 'weak'
  return 'progressing'
}

function statusLabel(item: KnowledgeNode) {
  return ({
    current: '当前课程',
    recommended: '推荐资源',
    mastered: '已掌握',
    unlearned: '未学习',
    weak: '薄弱',
    progressing: '学习中',
  } as Record<string, string>)[masteryStatus(item)]
}

function relationGroup(edge: KnowledgeEdge): RelationGroup {
  if (edge.type === 'resource') return 'resource'
  if (edge.type === 'path') return 'prerequisite'
  return 'hierarchy'
}

function showNotice(message: string) {
  notice.value = message
  if (noticeTimer) window.clearTimeout(noticeTimer)
  noticeTimer = window.setTimeout(() => {
    notice.value = ''
    noticeTimer = null
  }, 3600)
}

const selectedCourseInfo = computed(() => graph.value.courses.find((item) => item.id === selectedCourse.value))
const courseNode = computed(() => graph.value.nodes.find((item) => nodeKind(item) === 'course') || null)
const allWeakNodes = computed(() => graph.value.nodes
  .filter((item) => !['course', 'resource'].includes(nodeKind(item)) && masteryValue(item.mastery) < 60)
  .sort((a, b) => masteryValue(a.mastery) - masteryValue(b.mastery)))

const workspacePipeline = computed<Array<{ name: string; status?: string; count?: number }>>(
  () => workspace.value?.summary?.pipeline || [],
)
const readyPipelineCount = computed(() => workspacePipeline.value.filter((item) => item.status === 'ready').length)

function matchesMastery(item: KnowledgeNode) {
  if (masteryFilter.value === 'all' || nodeKind(item) === 'course') return true
  const score = masteryValue(item.mastery)
  if (masteryFilter.value === 'mastered') return score >= 80
  if (masteryFilter.value === 'weak') return score > 0 && score < 60
  if (masteryFilter.value === 'unlearned') return score <= 0
  return score < 70
}

const filteredNodes = computed(() => {
  const directlyMatched = graph.value.nodes.filter((item) => {
    const matchesLevel = levelFilter.value === 'all' || nodeKind(item) === levelFilter.value
    return matchesLevel && matchesMastery(item)
  })
  if (!directlyMatched.length) return []

  const keep = new Set(directlyMatched.map((item) => item.id))
  const incoming = new Map<string, string[]>()
  graph.value.edges.forEach((edge) => {
    if (edge.type === 'path') return
    incoming.set(edge.target, [...(incoming.get(edge.target) || []), edge.source])
  })
  const pending = [...keep]
  while (pending.length) {
    const id = pending.pop()!
    for (const parentId of incoming.get(id) || []) {
      if (keep.has(parentId)) continue
      keep.add(parentId)
      pending.push(parentId)
    }
  }
  if (courseNode.value) keep.add(courseNode.value.id)
  return graph.value.nodes.filter((item) => keep.has(item.id))
})

const filteredNodeIds = computed(() => new Set(filteredNodes.value.map((item) => item.id)))

const selectedNode = computed(() => (
  filteredNodes.value.find((item) => item.id === selectedNodeId.value)
  || filteredNodes.value[0]
  || null
))

const selectedConnections = computed(() => {
  if (!selectedNode.value) return []
  const ids = new Set<string>()
  graph.value.edges.forEach((edge) => {
    if (edge.source === selectedNode.value?.id) ids.add(edge.target)
    if (edge.target === selectedNode.value?.id) ids.add(edge.source)
  })
  return graph.value.nodes.filter((item) => ids.has(item.id))
})

const relatedResources = computed(() => {
  if (!selectedNode.value) return []
  const direct = selectedConnections.value.filter((item) => nodeKind(item) === 'resource')
  if (direct.length) return direct.slice(0, 4)
  const selectedTerms = new Set([
    nodeName(selectedNode.value),
    ...(selectedNode.value.keywords || []),
  ].map((item) => item.toLowerCase()))
  return graph.value.nodes
    .filter((item) => nodeKind(item) === 'resource')
    .map((item) => ({
      item,
      score: [nodeName(item), ...(item.keywords || [])]
        .map((value) => value.toLowerCase())
        .filter((value) => [...selectedTerms].some((term) => value.includes(term) || term.includes(value))).length,
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 4)
    .map(({ item }) => item)
})

const relatedKnowledge = computed(() => selectedConnections.value
  .filter((item) => nodeKind(item) !== 'resource')
  .slice(0, 5))

const selectedAdvice = computed(() => {
  if (!selectedNode.value) return '选择一个节点后，系统会结合掌握度给出学习建议。'
  if (!Number(selectedNode.value.evidence_count || 0)) return '当前没有个人掌握证据，可通过相关练习形成记录。'
  const score = masteryValue(selectedNode.value.mastery)
  if (nodeKind(selectedNode.value) === 'resource') return '建议把该资源与对应章节一起学习，完成后返回知识图谱记录掌握度。'
  if (score <= 0) return '先阅读核心讲解建立概念框架，再完成一组基础练习校准理解。'
  if (score < 60) return '这是当前薄弱点，建议先补看配套讲解，再用针对性练习验证关键概念。'
  if (score < 80) return '基础已经形成，适合通过迁移题与真实案例把理解推进到稳定掌握。'
  return '掌握度良好，可进入关联章节或加入学习路径进行间隔复习。'
})

const matchedNodeIds = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) return new Set<string>()
  return new Set(graph.value.nodes
    .filter((item) => [nodeName(item), item.desc || '', ...(item.keywords || [])].join(' ').toLowerCase().includes(query))
    .map((item) => item.id))
})

const pathNodeIds = computed(() => {
  const keep = new Set<string>()
  if (!selectedNode.value) return keep
  keep.add(selectedNode.value.id)
  if (nodeKind(selectedNode.value) === 'course') {
    filteredNodes.value.forEach((item) => keep.add(item.id))
    return keep
  }

  const incoming = new Map<string, string[]>()
  graph.value.edges.forEach((edge) => {
    if (edge.type === 'path') return
    incoming.set(edge.target, [...(incoming.get(edge.target) || []), edge.source])
  })
  const pending = [selectedNode.value.id]
  while (pending.length) {
    const id = pending.pop()!
    for (const parentId of incoming.get(id) || []) {
      if (keep.has(parentId)) continue
      keep.add(parentId)
      pending.push(parentId)
    }
  }
  if (nodeKind(selectedNode.value) === 'chapter') {
    graph.value.edges
      .filter((edge) => edge.source === selectedNode.value?.id && edge.type === 'knowledge')
      .forEach((edge) => keep.add(edge.target))
  }
  return keep
})

const graphStats = computed(() => {
  const resources = graph.value.nodes.filter((item) => nodeKind(item) === 'resource').length
  return [
    { label: '章节模块', value: graph.value.nodes.filter((item) => nodeKind(item) === 'chapter').length, icon: BookOpen },
    { label: '核心知识点', value: graph.value.nodes.filter((item) => nodeKind(item) === 'concept').length, icon: Layers3 },
    { label: '薄弱节点', value: allWeakNodes.value.length, icon: Target },
    { label: '资源 / 题型', value: resources, icon: FileText },
  ]
})

const graphLayout = computed(() => {
  const width = Math.max(920, Math.floor(viewportWidth.value))
  const nodeHeight = 58
  const chapterNodeHeight = 72
  const rowGap = 10
  const groupGap = 20
  const top = 24
  const root = filteredNodes.value.find((item) => nodeKind(item) === 'course')
  const chapters = filteredNodes.value.filter((item) => nodeKind(item) === 'chapter')
  const concepts = filteredNodes.value.filter((item) => nodeKind(item) === 'concept')
  const resources = filteredNodes.value.filter((item) => nodeKind(item) === 'resource')
  const conceptParents = new Map<string, string>()
  graph.value.edges.forEach((edge) => {
    if (edge.type === 'knowledge' && !conceptParents.has(edge.target)) conceptParents.set(edge.target, edge.source)
  })
  const groupedConcepts = new Map<string, KnowledgeNode[]>()
  chapters.forEach((item) => groupedConcepts.set(item.id, []))
  const orphanConcepts: KnowledgeNode[] = []
  concepts.forEach((item) => {
    const parentId = conceptParents.get(item.id)
    if (parentId && groupedConcepts.has(parentId)) groupedConcepts.get(parentId)!.push(item)
    else orphanConcepts.push(item)
  })

  const x = {
    course: Math.round(width * 0.025),
    chapter: Math.round(width * 0.285),
    concept: Math.round(width * 0.545),
    resource: Math.round(width * 0.81),
  }
  const nodeWidth = {
    course: Math.max(158, Math.round(width * 0.19)),
    chapter: Math.max(154, Math.round(width * 0.18)),
    concept: Math.max(172, Math.round(width * 0.205)),
    resource: Math.max(150, Math.round(width * 0.165)),
  }
  const positioned: PositionedNode[] = []
  let cursor = top
  chapters.forEach((chapter, chapterIndex) => {
    const children = groupedConcepts.get(chapter.id) || []
    const blockHeight = Math.max(82, children.length * (nodeHeight + rowGap) - rowGap)
    positioned.push({
      node: chapter,
      x: x.chapter,
      y: cursor + Math.max(0, (blockHeight - chapterNodeHeight) / 2),
      width: nodeWidth.chapter,
      height: chapterNodeHeight,
      index: chapterIndex + 1,
    })
    children.forEach((concept, conceptIndex) => positioned.push({
      node: concept,
      x: x.concept,
      y: cursor + conceptIndex * (nodeHeight + rowGap),
      width: nodeWidth.concept,
      height: nodeHeight,
      index: conceptIndex + 1,
    }))
    cursor += blockHeight + groupGap
  })

  orphanConcepts.forEach((concept, conceptIndex) => {
    positioned.push({
      node: concept,
      x: x.concept,
      y: cursor + conceptIndex * (nodeHeight + rowGap),
      width: nodeWidth.concept,
      height: nodeHeight,
      index: conceptIndex + 1,
    })
  })
  if (orphanConcepts.length) cursor += orphanConcepts.length * (nodeHeight + rowGap) + groupGap
  const height = Math.max(520, cursor + top - groupGap)

  if (root) positioned.push({
    node: root,
    x: x.course,
    y: Math.max(top, (height - nodeHeight) / 2),
    width: nodeWidth.course,
    height: nodeHeight + 12,
    index: 1,
  })
  resources.forEach((resource, resourceIndex) => positioned.push({
    node: resource,
    x: x.resource,
    y: Math.max(top, ((resourceIndex + 0.5) * height / Math.max(1, resources.length)) - nodeHeight / 2),
    width: nodeWidth.resource,
    height: nodeHeight,
    index: resourceIndex + 1,
  }))

  const byId = new Map(positioned.map((item) => [item.node.id, item]))
  const edges: PositionedEdge[] = graph.value.edges
    .filter((edge) => (
      filteredNodeIds.value.has(edge.source)
      && filteredNodeIds.value.has(edge.target)
      && relationVisibility.value[relationGroup(edge)]
      && byId.has(edge.source)
      && byId.has(edge.target)
    ))
    .map((edge) => {
      const source = byId.get(edge.source)!
      const target = byId.get(edge.target)!
      const sx = source.x + source.width
      const sy = source.y + source.height / 2
      const tx = target.x
      const ty = target.y + target.height / 2
      let d = ''
      if (Math.abs(source.x - target.x) < 24) {
        const bendX = source.x - 24
        d = `M ${source.x} ${sy} C ${bendX} ${sy}, ${bendX} ${ty}, ${target.x} ${ty}`
      } else {
        const midX = sx + Math.max(28, (tx - sx) * 0.5)
        d = `M ${sx} ${sy} C ${midX} ${sy}, ${midX} ${ty}, ${tx} ${ty}`
      }
      return { ...edge, d, group: relationGroup(edge) }
    })
  return { width, height, nodes: positioned, edges }
})

const graphZoomStyle = computed(() => ({
  width: `${graphLayout.value.width * graphZoom.value}px`,
  minHeight: `${34 + graphLayout.value.height * graphZoom.value}px`,
}))

const graphZoomLayerStyle = computed(() => ({
  width: `${graphLayout.value.width}px`,
  height: `${graphLayout.value.height}px`,
  transform: `scale(${graphZoom.value})`,
}))

function nodeGlyph(item: PositionedNode) {
  if (nodeKind(item.node) === 'course') return '课'
  if (nodeKind(item.node) === 'chapter') return String(item.index)
  if (nodeKind(item.node) === 'resource') return nodeName(item.node).includes('题') ? '题' : '资'
  return ''
}

type ConceptIconChoice = {
  key: string
  icon: Component
}

const conceptIconRules: Array<ConceptIconChoice & { pattern: RegExp }> = [
  { key: 'process', icon: Workflow, pattern: /进程|线程|调度|并发|同步|互斥|死锁/i },
  { key: 'kernel', icon: Cpu, pattern: /内核|中断|系统调用|处理器|\bcpu\b/i },
  { key: 'memory', icon: MemoryStick, pattern: /内存|虚拟|页表|缓存|地址|段页/i },
  { key: 'storage', icon: HardDrive, pattern: /磁盘|文件|目录|分区|存储|\bmbr\b|\bbios\b/i },
  { key: 'boot', icon: Power, pattern: /启动|\bboot\b/i },
  { key: 'guide', icon: Compass, pattern: /引导|导航/i },
  { key: 'application', icon: Terminal, pattern: /应用|程序|指令|命令|编译|代码|\bshell\b/i },
  { key: 'network', icon: Network, pattern: /网络|协议|通信|\bsocket\b/i },
  { key: 'management', icon: Settings2, pattern: /管理|机制|策略|控制/i },
  { key: 'architecture', icon: Boxes, pattern: /体系|结构|架构|原理|概述|概论/i },
]

function conceptIconChoice(item: KnowledgeNode): ConceptIconChoice {
  const searchable = [
    nodeName(item),
    item.category || '',
    item.chapter || '',
    item.desc || '',
    ...(item.keywords || []),
  ].join(' ')
  return conceptIconRules.find((rule) => rule.pattern.test(searchable)) || {
    key: 'concept',
    icon: BrainCircuit,
  }
}

function nodeClass(item: PositionedNode) {
  const isDimmed = focusPath.value && !pathNodeIds.value.has(item.node.id)
  return [
    'kg-node',
    `type-${nodeKind(item.node)}`,
    `status-${masteryStatus(item.node)}`,
    {
      selected: item.node.id === selectedNodeId.value,
      dimmed: isDimmed,
      path: focusPath.value && pathNodeIds.value.has(item.node.id),
      matched: matchedNodeIds.value.has(item.node.id),
    },
  ]
}

function edgeClass(edge: PositionedEdge) {
  const active = edge.source === selectedNodeId.value || edge.target === selectedNodeId.value
  const dimmed = focusPath.value && (!pathNodeIds.value.has(edge.source) || !pathNodeIds.value.has(edge.target))
  return [
    'kg-edge',
    edge.group === 'prerequisite' ? 'edge-path' : `edge-${edge.group}`,
    { active, dimmed, flowing: focusPath.value && !dimmed },
  ]
}

function ringStyle(value: unknown) {
  return { '--score': `${masteryValue(value) * 3.6}deg` }
}

function selectNode(nodeId: string) {
  selectedNodeId.value = nodeId
  selectedSearchResult.value = null
  const item = graph.value.nodes.find((node) => node.id === nodeId)
  if (item) {
    graphInteractionStatus.value = `已选择${nodeName(item)}，右侧已同步节点证据与学习动作。`
    showNotice(`已定位“${nodeName(item)}”，右侧已同步节点证据与学习动作。`)
  }
}

function ensureSelection() {
  if (filteredNodes.value.some((item) => item.id === selectedNodeId.value)) return
  selectedNodeId.value = filteredNodes.value[0]?.id || ''
}

function clampGraphZoom(value: number) {
  return Math.max(GRAPH_ZOOM_MIN, Math.min(GRAPH_ZOOM_MAX, Number(value.toFixed(2))))
}

function setGraphZoom(value: number, announce = true) {
  const next = clampGraphZoom(value)
  graphZoom.value = next
  if (announce) {
    const percent = Math.round(next * 100)
    graphInteractionStatus.value = `知识图谱缩放至${percent}%。`
    showNotice(`知识图谱已缩放至 ${percent}%。`)
  }
}

function resetGraphZoom() {
  setGraphZoom(1)
}

function fitGraphToViewport() {
  const viewport = graphViewport.value
  if (!viewport || !graphLayout.value.width) {
    resetGraphZoom()
    return
  }
  const widthRatio = viewport.clientWidth / graphLayout.value.width
  const heightRatio = Math.max(0, (viewport.clientHeight - 44) / graphLayout.value.height)
  setGraphZoom(Math.min(1, widthRatio, heightRatio))
}

function handleGraphWheel(event: WheelEvent) {
  if (!event.ctrlKey && !event.metaKey) return
  event.preventDefault()
  setGraphZoom(graphZoom.value + (event.deltaY > 0 ? -GRAPH_ZOOM_STEP : GRAPH_ZOOM_STEP), false)
  graphInteractionStatus.value = `知识图谱缩放至${Math.round(graphZoom.value * 100)}%。`
}

function handleGraphZoomInput(event: Event) {
  setGraphZoom(Number((event.target as HTMLInputElement).value), false)
  graphInteractionStatus.value = `知识图谱缩放至${Math.round(graphZoom.value * 100)}%。`
}

function graphNodeButton(nodeId: string) {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-knowledge-node]'))
    .find((element) => element.dataset.knowledgeNode === nodeId) || null
}

function focusGraphNode(nodeId: string) {
  nextTick(() => graphNodeButton(nodeId)?.focus())
}

function moveGraphSelection(nodeId: string, direction: 'left' | 'right' | 'up' | 'down') {
  const current = graphLayout.value.nodes.find((item) => item.node.id === nodeId)
  if (!current) return
  const candidates = graphLayout.value.nodes.filter((item) => item.node.id !== nodeId).map((item) => {
    const dx = item.x + item.width / 2 - (current.x + current.width / 2)
    const dy = item.y + item.height / 2 - (current.y + current.height / 2)
    const inDirection = direction === 'left' ? dx < -8 : direction === 'right' ? dx > 8 : direction === 'up' ? dy < -8 : dy > 8
    return { item, dx, dy, inDirection }
  }).filter((item) => item.inDirection)
  if (!candidates.length) return
  candidates.sort((a, b) => {
    const primaryA = direction === 'left' || direction === 'right' ? Math.abs(a.dx) : Math.abs(a.dy)
    const primaryB = direction === 'left' || direction === 'right' ? Math.abs(b.dx) : Math.abs(b.dy)
    const secondaryA = direction === 'left' || direction === 'right' ? Math.abs(a.dy) : Math.abs(a.dx)
    const secondaryB = direction === 'left' || direction === 'right' ? Math.abs(b.dy) : Math.abs(b.dx)
    return (secondaryA * 4 + primaryA) - (secondaryB * 4 + primaryB)
  })
  selectNode(candidates[0].item.node.id)
  focusGraphNode(candidates[0].item.node.id)
}

function handleGraphNodeKeydown(event: KeyboardEvent, nodeId: string) {
  const direction = ({ ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' } as Record<string, 'left' | 'right' | 'up' | 'down'>)[event.key]
  if (direction) {
    event.preventDefault()
    moveGraphSelection(nodeId, direction)
    return
  }
  if (event.key === 'Home' || event.key === 'End') {
    event.preventDefault()
    const target = event.key === 'Home'
      ? graphLayout.value.nodes.find((item) => nodeKind(item.node) === 'course') || graphLayout.value.nodes[0]
      : [...graphLayout.value.nodes].reverse().find((item) => nodeKind(item.node) === 'resource') || graphLayout.value.nodes[graphLayout.value.nodes.length - 1]
    if (target) {
      selectNode(target.node.id)
      focusGraphNode(target.node.id)
    }
    return
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    if (isFullscreen.value) void exitFullscreen()
    else (event.currentTarget as HTMLElement).blur()
  }
}

async function loadWorkspace() {
  workspaceLoading.value = true
  workspaceError.value = ''
  try {
    workspace.value = await getKnowledgeWorkspace(studentId.value)
  } catch (reason: any) {
    workspaceError.value = reason?.message || '知识证据处理状态暂时不可用。'
  } finally {
    workspaceLoading.value = false
  }
}

async function loadGraph(options: { initial?: boolean; preserveSelection?: boolean } = {}) {
  const { initial = false, preserveSelection = true } = options
  const previousNodeId = preserveSelection ? selectedNodeId.value : ''
  if (initial) graphLoading.value = true
  else refreshing.value = true
  graphError.value = ''
  try {
    const graphData = await getKnowledgeGraph(studentId.value, {
      sourceType: sourceType.value,
      course: selectedCourse.value,
      maxNodes: 24,
    }) as KnowledgeGraph
    graph.value = {
      ...emptyGraph(),
      ...graphData,
      nodes: Array.isArray(graphData?.nodes) ? graphData.nodes : [],
      edges: Array.isArray(graphData?.edges) ? graphData.edges : [],
      courses: Array.isArray(graphData?.courses) ? graphData.courses : [],
      legend: Array.isArray(graphData?.legend) ? graphData.legend : [],
      stats: graphData?.stats || {},
    }
    selectedCourse.value = graph.value.selected_course || selectedCourse.value
    selectedNodeId.value = graph.value.nodes.some((item) => item.id === previousNodeId)
      ? previousNodeId
      : (graph.value.nodes[0]?.id || '')
    await nextTick()
    updateViewportWidth()
  } catch (reason: any) {
    graphError.value = reason?.message || '课程知识图谱加载失败'
  } finally {
    graphLoading.value = false
    refreshing.value = false
  }
}

async function loadPage() {
  await Promise.allSettled([
    loadWorkspace(),
    loadGraph({ initial: true, preserveSelection: false }),
  ])
}

function chooseTextbook() {
  if (!uploadingTextbook.value) textbookInput.value?.click()
}

async function uploadTextbook(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploadingTextbook.value = true
  graphError.value = ''
  try {
    const response = await fetch(`/api/knowledge/textbook?student_id=${encodeURIComponent(studentId.value)}&filename=${encodeURIComponent(file.name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
    })
    const result = await response.json().catch(() => ({}))
    if (!response.ok || !result.success) throw new Error(result?.error?.message || '电子教材处理失败')
    selectedCourse.value = result.data.course_id
    sourceType.value = 'all'
    await Promise.all([loadWorkspace(), loadGraph({ initial: true, preserveSelection: false })])
    showNotice(`《${file.name.replace(/\.[^.]+$/, '')}》已生成 ${result.data.chapter_count} 章知识结构`)
  } catch (reason: any) {
    graphError.value = reason?.message || '电子教材上传失败'
  } finally {
    uploadingTextbook.value = false
    input.value = ''
  }
}

async function runSearch() {
  const query = keyword.value.trim()
  searchAttempted.value = true
  selectedSearchResult.value = null
  searchError.value = ''
  if (!query) {
    searchResults.value = []
    searchError.value = '请输入概念、章节或资源名称。'
    return
  }
  const localMatch = graph.value.nodes.find((item) => matchedNodeIds.value.has(item.id))
  if (localMatch) selectedNodeId.value = localMatch.id
  searching.value = true
  try {
    searchResults.value = await searchKnowledge(studentId.value, query) as SearchResult[]
    showNotice(localMatch
      ? `已在课程图谱中定位“${nodeName(localMatch)}”，并检索到 ${searchResults.value.length} 条知识证据。`
      : `知识库检索完成，共找到 ${searchResults.value.length} 条相关证据。`)
  } catch (reason: any) {
    searchResults.value = []
    searchError.value = reason?.message || '知识检索失败'
  } finally {
    searching.value = false
  }
}

function findGraphNode(item: SearchResult) {
  const title = item.title || item.name || ''
  return graph.value.nodes.find((node) => node.id === item.id || nodeName(node) === title)
}

function openSearchResult(item: SearchResult) {
  selectedSearchResult.value = item
  const match = findGraphNode(item)
  if (match) {
    selectedNodeId.value = match.id
    showNotice(`已把检索证据映射到图谱节点“${nodeName(match)}”。`)
  } else {
    showNotice(`已展开“${item.title || item.name || '检索证据'}”，它暂未映射为当前课程节点。`)
  }
}

function clearSearch() {
  keyword.value = ''
  searchResults.value = []
  selectedSearchResult.value = null
  searchAttempted.value = false
  searchError.value = ''
}

async function setSourceFilter(value: string) {
  sourceType.value = value
  await loadGraph({ preserveSelection: false })
  showNotice(value === 'all' ? '已显示课程结构与生成资源。' : value === 'course' ? '已聚焦课程层级。' : '已聚焦生成资源。')
}

function setLevelFilter(value: 'all' | NodeKind) {
  levelFilter.value = value
  nextTick(ensureSelection)
}

function setMasteryFilter(value: MasteryFilter) {
  masteryFilter.value = value
  nextTick(ensureSelection)
}

function toggleRelation(group: RelationGroup) {
  relationVisibility.value[group] = !relationVisibility.value[group]
  showNotice(`${relationVisibility.value[group] ? '已显示' : '已隐藏'}${({ hierarchy: '层级包含', prerequisite: '学习顺序', resource: '配套资源' } as Record<RelationGroup, string>)[group]}关系。`)
}

function resetFilters() {
  levelFilter.value = 'all'
  masteryFilter.value = 'all'
  relationVisibility.value = { hierarchy: true, prerequisite: true, resource: true }
  focusPath.value = false
  ensureSelection()
  showNotice('筛选条件已重置，恢复完整课程图谱。')
}

function toggleFocusPath() {
  focusPath.value = !focusPath.value
  showNotice(focusPath.value ? '已高亮当前节点的课程归属与学习链路。' : '已恢复完整关系视图。')
}

function lockBodyForFullscreen() {
  if (!isFullscreen.value) return
  if (!bodyOverflowLocked) {
    previousBodyOverflow = document.body.style.overflow
    bodyOverflowLocked = true
  }
  document.body.style.overflow = 'hidden'
}

function restoreBodyAfterFullscreen() {
  if (!bodyOverflowLocked) return
  document.body.style.overflow = previousBodyOverflow
  previousBodyOverflow = ''
  bodyOverflowLocked = false
}

function syncFullscreenState() {
  const nativeFullscreen = document.fullscreenElement === knowledgeRoot.value
  if (nativeFullscreen) {
    fullscreenFallback = false
    isFullscreen.value = true
    lockBodyForFullscreen()
  } else if (!fullscreenFallback) {
    const wasFullscreen = isFullscreen.value
    isFullscreen.value = false
    restoreBodyAfterFullscreen()
    if (wasFullscreen) nextTick(() => fullscreenTrigger.value?.focus())
  }
  nextTick(updateViewportWidth)
}

async function enterFullscreen() {
  if (knowledgeRoot.value?.requestFullscreen && document.fullscreenEnabled) {
    try {
      await knowledgeRoot.value.requestFullscreen()
      return
    } catch {
      // Some embedded browsers block the native API; use the visual fallback below.
    }
  }
  fullscreenFallback = true
  isFullscreen.value = true
  lockBodyForFullscreen()
  graphInteractionStatus.value = '已进入图谱全屏模式。'
  nextTick(updateViewportWidth)
}

async function exitFullscreen() {
  fullscreenFallback = false
  if (document.fullscreenElement) {
    try {
      await document.exitFullscreen()
    } catch {
      // Keep the fallback cleanup below even if the browser refuses the request.
    }
  }
  isFullscreen.value = false
  restoreBodyAfterFullscreen()
  graphInteractionStatus.value = '已退出图谱全屏模式。'
  nextTick(() => {
    updateViewportWidth()
    fullscreenTrigger.value?.focus()
  })
}

async function toggleFullscreen() {
  if (isFullscreen.value) await exitFullscreen()
  else await enterFullscreen()
}

function toggleMobilePanel(panel: 'filters' | 'details') {
  mobilePanel.value = mobilePanel.value === panel ? 'none' : panel
}

function updateViewportWidth() {
  if (graphViewport.value) viewportWidth.value = graphViewport.value.clientWidth
}

function openResource(item: KnowledgeNode) {
  selectNode(item.id)
  if (item.source_path && /^https?:\/\//i.test(item.source_path)) {
    window.open(item.source_path, '_blank', 'noopener,noreferrer')
    showNotice(`已在新窗口打开“${nodeName(item)}”。`)
    return
  }
  void router.push({ path: '/workshop', query: { resource: item.id, topic: nodeName(item) } })
}

async function generateExercise() {
  if (!selectedNode.value || generatingExercise.value) return
  const node = selectedNode.value
  generatingExercise.value = true
  graphError.value = ''
  showNotice(`正在围绕“${nodeName(node)}”调用 GLM 重新生成题库。`)
  try {
    const path = await getPathOverview(studentId.value)
    const stage = path.current_stage || (path.nodes || []).find((item: any) => ['current', 'active', 'warning'].includes(String(item.status)))
    if (!stage?.id) throw new Error('请先在路径推送中生成学习路径，再为知识节点生成练习。')
    const result = await generatePathStageQuestions(studentId.value, {
      stageId: String(stage.id),
      knowledgeNodeId: node.id,
      topic: nodeName(node),
      topicDescription: node.desc || node.chapter || node.source_title || '',
      difficulty: 'mixed',
      count: 8,
      questionTypes: ['single_choice', 'multiple_choice', 'true_false'],
      typeCounts: { single_choice: 4, multiple_choice: 2, true_false: 2 },
    })
    const bank = result?.question_bank
    if (!bank?.id) throw new Error('GLM 没有返回可用的新题库。')
    showNotice(`“${nodeName(node)}”的新题库已生成，正在载入练习诊断。`)
    await router.push({
      path: '/exercise',
      query: { topic: nodeName(node), node: node.id, stage: stage.id, bank: bank.id, autostart: '1' },
    })
  } catch (reason: any) {
    graphError.value = reason?.message || '知识节点题库生成失败'
  } finally {
    generatingExercise.value = false
  }
}

async function addToPath() {
  if (!selectedNode.value || addingToPath.value) return
  const node = selectedNode.value
  addingToPath.value = true
  graphError.value = ''
  try {
    const result = await addKnowledgeBranchToPath(studentId.value, {
      id: node.id,
      title: nodeName(node),
      description: node.desc || node.chapter || node.source_title || '',
      mastery: masteryValue(node.mastery),
    })
    const parentTitle = result?.parent_stage?.title || '当前学习节点'
    const branchTitle = result?.branch?.title || nodeName(node)
    showNotice(
      result?.created
        ? `已在“${parentTitle}”下生成分支“${branchTitle}”。`
        : `“${branchTitle}”已在当前节点的分支中。`,
    )
    await router.push({ path: '/path', query: { branch: result?.branch?.id || '' } })
  } catch (reason: any) {
    graphError.value = reason?.message || '知识分支加入路径失败'
  } finally {
    addingToPath.value = false
  }
}

function isTypingTarget(target: EventTarget | null) {
  const element = target as HTMLElement | null
  return Boolean(element?.matches('input, textarea, select, [contenteditable="true"]'))
}

function handleKeydown(event: KeyboardEvent) {
  if (isTypingTarget(event.target)) return
  if (event.key === 'Escape') {
    if (isFullscreen.value) {
      event.preventDefault()
      void exitFullscreen()
    } else if (mobilePanel.value !== 'none') {
      event.preventDefault()
      mobilePanel.value = 'none'
    }
    return
  }
  if (event.key === '+' || event.key === '=') {
    event.preventDefault()
    setGraphZoom(graphZoom.value + GRAPH_ZOOM_STEP)
    return
  }
  if (event.key === '-' || event.key === '_') {
    event.preventDefault()
    setGraphZoom(graphZoom.value - GRAPH_ZOOM_STEP)
    return
  }
  if (event.key === '0') {
    event.preventDefault()
    resetGraphZoom()
    return
  }
  if (event.key.toLowerCase() === 'f') {
    event.preventDefault()
    void toggleFullscreen()
  }
}

watch(filteredNodes, () => nextTick(ensureSelection))

onMounted(() => {
  void loadPage()
  window.addEventListener('keydown', handleKeydown)
  document.addEventListener('fullscreenchange', syncFullscreenState)
  resizeObserver = new ResizeObserver(updateViewportWidth)
  if (graphViewport.value) resizeObserver.observe(graphViewport.value)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('fullscreenchange', syncFullscreenState)
  resizeObserver?.disconnect()
  if (noticeTimer) window.clearTimeout(noticeTimer)
  if (document.fullscreenElement === knowledgeRoot.value) void document.exitFullscreen().catch(() => undefined)
  fullscreenFallback = false
  restoreBodyAfterFullscreen()
})
</script>

<template>
  <main
    ref="knowledgeRoot"
    class="knowledge-course-map"
    :class="{
      fullscreen: isFullscreen,
      compact: filtersCollapsed,
      'show-filter-panel': mobilePanel === 'filters',
      'show-detail-panel': mobilePanel === 'details',
    }"
  >
    <button
      v-if="mobilePanel !== 'none'"
      class="mobile-panel-backdrop"
      type="button"
      aria-label="关闭当前面板"
      @click="mobilePanel = 'none'"
    ></button>
    <aside id="knowledge-filter-panel" class="course-filter-panel" aria-label="课程图谱筛选">
      <header class="panel-heading">
        <span><Filter :size="19" /></span>
        <div><small>KNOWLEDGE HUB</small><strong>知识中枢</strong></div>
      </header>

      <section class="filter-unit source-unit">
        <label for="course-select">课程文档</label>
        <select id="course-select" v-model="selectedCourse" :disabled="graphLoading" @change="loadGraph({ preserveSelection: false })">
          <option v-if="!graph.courses.length" value="">暂无课程</option>
          <option v-for="course in graph.courses" :key="course.id" :value="course.id">{{ course.title }}</option>
        </select>
        <p>{{ graph.course_summary || '选择课程后，系统会提取章节、知识点与配套资源。' }}</p>
        <input ref="textbookInput" class="textbook-file-input" type="file" accept=".txt,.md,.pdf,.docx" @change="uploadTextbook" />
        <button class="textbook-upload-button" type="button" :disabled="uploadingTextbook" @click="chooseTextbook">
          <LoaderCircle v-if="uploadingTextbook" class="spin" :size="16" />
          <Upload v-else :size="16" />{{ uploadingTextbook ? '正在生成知识结构' : '上传电子教材' }}
        </button>
      </section>

      <section class="filter-unit">
        <label>知识来源</label>
        <div class="seg-grid">
          <button type="button" :class="{ active: sourceType === 'all' }" @click="setSourceFilter('all')">全量</button>
          <button type="button" :class="{ active: sourceType === 'course' }" @click="setSourceFilter('course')">课程</button>
          <button type="button" :class="{ active: sourceType === 'generated' }" @click="setSourceFilter('generated')">资源</button>
        </div>
      </section>

      <section class="filter-unit">
        <label>知识层级</label>
        <div class="seg-grid two level-grid">
          <button
            v-for="option in levelOptions"
            :key="option.value"
            type="button"
            :class="{ active: levelFilter === option.value }"
            @click="setLevelFilter(option.value)"
          >{{ option.label }}</button>
        </div>
      </section>

      <section class="filter-unit">
        <label>掌握状态</label>
        <div class="seg-grid two mastery-grid">
          <button
            v-for="option in masteryOptions"
            :key="option.value"
            type="button"
            :class="{ active: masteryFilter === option.value }"
            @click="setMasteryFilter(option.value)"
          >{{ option.label }}</button>
        </div>
      </section>

      <section class="filter-unit">
        <label>关系类型</label>
        <button class="relation-toggle" :class="{ active: relationVisibility.hierarchy }" type="button" :aria-pressed="relationVisibility.hierarchy" @click="toggleRelation('hierarchy')">
          <i></i><span>层级包含</span><CheckCircle2 :size="15" />
        </button>
        <button class="relation-toggle" :class="{ active: relationVisibility.prerequisite }" type="button" :aria-pressed="relationVisibility.prerequisite" @click="toggleRelation('prerequisite')">
          <i class="line-prerequisite"></i><span>学习顺序</span><CheckCircle2 :size="15" />
        </button>
        <button class="relation-toggle" :class="{ active: relationVisibility.resource }" type="button" :aria-pressed="relationVisibility.resource" @click="toggleRelation('resource')">
          <i class="line-resource"></i><span>配套资源</span><CheckCircle2 :size="15" />
        </button>
      </section>

      <form class="course-search" role="search" @submit.prevent="runSearch">
        <Search :size="15" />
        <input v-model="keyword" aria-label="搜索知识图谱" placeholder="搜索章节、知识点或资源" />
        <button type="submit" :disabled="searching || !keyword.trim()" aria-label="搜索">
          <LoaderCircle v-if="searching" class="spin" :size="14" />
          <span v-else>搜索</span>
        </button>
      </form>

      <div class="filter-command-grid">
        <button type="button" @click="resetFilters"><RefreshCw :size="14" />重置</button>
        <button class="primary" type="button" :disabled="refreshing" @click="loadGraph()">
          <LoaderCircle v-if="refreshing" class="spin" :size="14" />
          <GitBranch v-else :size="14" />{{ refreshing ? '重建中' : '重建图谱' }}
        </button>
      </div>
    </aside>

    <section class="course-graph-shell" aria-label="课程知识图谱工作区">
      <header class="course-graph-head">
        <div>
          <small><Database :size="14" /> KNOWLEDGE GRAPH</small>
          <h1>{{ graph.course ? `${graph.course}知识图谱` : '课程知识图谱' }}</h1>
          <p>{{ graph.course_summary || '按课程、章节、核心知识点和配套资源构建学习结构。' }}</p>
        </div>
        <div class="graph-tools">
          <button class="mobile-panel-toggle" type="button" :aria-expanded="mobilePanel === 'filters'" aria-controls="knowledge-filter-panel" @click="toggleMobilePanel('filters')"><Filter :size="14" />筛选</button>
          <button class="mobile-panel-toggle" type="button" :aria-expanded="mobilePanel === 'details'" aria-controls="knowledge-detail-panel" @click="toggleMobilePanel('details')"><ClipboardList :size="14" />节点详情</button>
          <button ref="fullscreenTrigger" type="button" :aria-expanded="isFullscreen" :aria-label="isFullscreen ? '退出图谱全屏' : '进入图谱全屏'" :title="isFullscreen ? '退出图谱全屏 (F / Esc)' : '进入图谱全屏 (F)'" @click="toggleFullscreen">
            <Minimize2 v-if="isFullscreen" :size="14" />
            <Fullscreen v-else :size="14" />{{ isFullscreen ? '退出全屏' : '全屏' }}
          </button>
          <div class="graph-zoom-tools" role="group" aria-label="图谱缩放控制">
            <button type="button" aria-label="缩小图谱" title="缩小图谱 (-)" :disabled="graphZoom <= GRAPH_ZOOM_MIN" @click="setGraphZoom(graphZoom - GRAPH_ZOOM_STEP)">−</button>
            <output class="graph-zoom-value" aria-live="polite">{{ Math.round(graphZoom * 100) }}%</output>
            <button type="button" aria-label="放大图谱" title="放大图谱 (+)" :disabled="graphZoom >= GRAPH_ZOOM_MAX" @click="setGraphZoom(graphZoom + GRAPH_ZOOM_STEP)">＋</button>
            <button type="button" aria-label="恢复图谱百分之百" title="恢复 100% (0)" :aria-pressed="graphZoom === 1" @click="resetGraphZoom">100%</button>
            <button type="button" aria-label="适配图谱到窗口" title="适配窗口" @click="fitGraphToViewport">适配</button>
            <input
              class="graph-zoom-slider"
              type="range"
              min="0.6"
              max="1.8"
              step="0.1"
              :value="graphZoom"
              aria-label="图谱缩放比例"
              @input="handleGraphZoomInput"
            />
          </div>
          <button class="desktop-filter-toggle" type="button" @click="filtersCollapsed = !filtersCollapsed">
            <PanelLeftOpen v-if="filtersCollapsed" :size="14" />
            <PanelLeftClose v-else :size="14" />{{ filtersCollapsed ? '展开筛选' : '收起筛选' }}
          </button>
          <button :class="{ active: focusPath }" type="button" :disabled="!selectedNode" @click="toggleFocusPath"><Route :size="14" />高亮路径</button>
        </div>
      </header>
      <span class="knowledge-sr-only" aria-live="polite">{{ graphInteractionStatus }}</span>

      <div v-if="graphError" class="graph-alert" role="alert">
        <AlertCircle :size="17" /><span>{{ graphError }}</span><button type="button" @click="loadGraph({ initial: true })">重新加载</button>
      </div>

      <div v-if="graphLoading" class="graph-loading" aria-live="polite">
        <span class="graph-spinner"><GitBranch :size="25" /></span>
        <strong>正在解析课程结构</strong>
        <small>同步章节、知识点、掌握度与配套资源…</small>
      </div>

      <div v-else-if="!graph.nodes.length" class="graph-loading graph-empty">
        <Database :size="28" /><strong>暂无可构建的课程知识</strong>
        <small>请上传电子教材，或确认原始课程资料库中已有可解析的教学文档。</small>
        <button type="button" @click="chooseTextbook">上传电子教材 <ArrowRight :size="14" /></button>
      </div>

      <div v-else-if="!filteredNodes.length" class="graph-loading graph-empty">
        <Filter :size="28" /><strong>没有符合当前筛选的节点</strong>
        <small>放宽掌握状态或知识层级筛选，即可恢复课程上下文。</small>
        <button type="button" @click="resetFilters">重置筛选</button>
      </div>

      <div v-else class="graph-stage">
        <div ref="graphViewport" class="graph-scroll" @wheel="handleGraphWheel">
          <div class="graph-inner" :style="graphZoomStyle">
            <div class="lane-heads">
              <span>课程入口</span><span>章节模块</span><span>核心知识点</span><span>资源 / 题型</span>
            </div>
            <div class="graph-zoom-layer" :style="graphZoomLayerStyle">
              <svg
                class="layered-graph"
                :width="graphLayout.width"
                :height="graphLayout.height"
                :viewBox="`0 0 ${graphLayout.width} ${graphLayout.height}`"
                role="img"
                :aria-label="`${graph.course}分层知识图谱，共${filteredNodes.length}个节点、${graphLayout.edges.length}条可见关系`"
              >
              <defs>
                <marker id="kg-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
                  <path d="M0,0 L7,3.5 L0,7 Z" fill="#8db5f2" />
                </marker>
              </defs>
              <g aria-hidden="true">
                <path
                  v-for="(edge, index) in graphLayout.edges"
                  :key="`${edge.source}-${edge.target}-${index}`"
                  :d="edge.d"
                  :class="edgeClass(edge)"
                  marker-end="url(#kg-arrow)"
                />
              </g>
              <foreignObject
                v-for="item in graphLayout.nodes"
                :key="item.node.id"
                :x="item.x"
                :y="item.y"
                :width="item.width"
                :height="item.height"
              >
                <button
                  xmlns="http://www.w3.org/1999/xhtml"
                  type="button"
                  :data-knowledge-node="item.node.id"
                  :class="nodeClass(item)"
                  :tabindex="item.node.id === selectedNodeId ? 0 : -1"
                  :aria-selected="item.node.id === selectedNodeId ? 'true' : 'false'"
                  :aria-label="`${nodeName(item.node)}，${nodeTypeLabel(item.node)}`"
                  @click="selectNode(item.node.id)"
                  @keydown="handleGraphNodeKeydown($event, item.node.id)"
                >
                  <span
                    class="node-icon"
                    :data-concept-icon="nodeKind(item.node) === 'concept' ? conceptIconChoice(item.node).key : undefined"
                  >
                    <component
                      :is="conceptIconChoice(item.node).icon"
                      v-if="nodeKind(item.node) === 'concept'"
                      :size="18"
                      :stroke-width="2.35"
                      aria-hidden="true"
                    />
                    <template v-else>{{ nodeGlyph(item) }}</template>
                  </span>
                  <span class="node-copy">
                    <strong>{{ nodeName(item.node) }}</strong>
                    <small>{{ nodeTypeLabel(item.node) }}</small>
                  </span>
                </button>
              </foreignObject>
              </svg>
            </div>
          </div>
        </div>
        <footer class="graph-legend">
          <span><i class="current"></i>当前课程</span>
          <span><i class="mastered"></i>已掌握</span>
          <span><i class="weak"></i>薄弱点</span>
          <span><i class="recommended"></i>推荐资源</span>
          <span><b></b>层级 / 顺序</span>
          <span><b class="dash"></b>资源关联</span>
        </footer>
      </div>

      <div v-if="graph.nodes.length" class="course-stat-row" aria-label="课程知识统计">
        <div v-for="item in graphStats" :key="item.label">
          <component :is="item.icon" :size="18" />
          <strong>{{ item.value }}</strong><span>{{ item.label }}</span>
        </div>
      </div>
    </section>

    <aside id="knowledge-detail-panel" class="course-detail-panel" aria-label="节点详情">
      <header class="detail-head">
        <div><small><CircleDot :size="14" /> NODE DETAIL</small><strong>知识点详情</strong></div>
        <span>{{ selectedNode ? nodeTypeLabel(selectedNode) : '等待选择' }}</span>
      </header>

      <template v-if="selectedNode">
        <section class="selected-node-card">
          <div class="detail-avatar" :class="`status-${masteryStatus(selectedNode)}`">
            <GraduationCap v-if="nodeKind(selectedNode) === 'course'" :size="27" />
            <BookOpen v-else-if="nodeKind(selectedNode) === 'chapter'" :size="25" />
            <BrainCircuit v-else-if="nodeKind(selectedNode) === 'concept'" :size="25" />
            <FileText v-else :size="25" />
          </div>
          <div>
            <span class="node-type">{{ statusLabel(selectedNode) }}</span>
            <h2>{{ nodeName(selectedNode) }}</h2>
            <p>来自 {{ selectedNode.source_title || graph.course || '课程知识库' }}</p>
          </div>
        </section>

        <section class="mastery-block">
          <div class="score-ring" :style="ringStyle(selectedNode.mastery)"><strong>{{ selectedNode.evidence_count ? `${masteryValue(selectedNode.mastery).toFixed(0)}%` : '未评估' }}</strong></div>
          <div><h3>当前掌握度</h3><p>{{ selectedAdvice }}</p></div>
        </section>

        <section class="detail-block node-evidence">
          <h3>节点证据</h3>
          <p>{{ selectedNode.desc || '该节点来自课程资料、生成资源和学习行为的结构化解析。' }}</p>
          <dl>
            <div><dt>节点类型</dt><dd>{{ nodeTypeLabel(selectedNode) }}</dd></div>
            <div><dt>关联关系</dt><dd>{{ selectedNode.relation_count ?? selectedConnections.length }} 条</dd></div>
            <div><dt>数据来源</dt><dd>{{ sourceLabel(selectedNode.source_type) }}</dd></div>
          </dl>
          <div v-if="selectedNode.keywords?.length" class="pill-wrap">
            <span v-for="item in selectedNode.keywords.slice(0, 6)" :key="item">{{ item }}</span>
          </div>
        </section>

        <section v-if="relatedResources.length" class="detail-block">
          <h3>配套资源</h3>
          <div class="resource-links">
            <button v-for="item in relatedResources" :key="item.id" type="button" @click="openResource(item)">
              <FileText :size="14" /><span>{{ nodeName(item) }}</span><ChevronRight :size="14" />
            </button>
          </div>
        </section>

        <section v-if="relatedKnowledge.length" class="detail-block">
          <h3>关联知识</h3>
          <div class="pill-wrap linked-pills">
            <button v-for="item in relatedKnowledge" :key="item.id" type="button" @click="selectNode(item.id)">{{ nodeName(item) }}</button>
          </div>
        </section>

        <section v-if="searchAttempted" class="result-list">
          <header><h3>知识库检索</h3><button type="button" aria-label="清除检索" @click="clearSearch"><X :size="14" /></button></header>
          <p v-if="searchError" class="inline-error">{{ searchError }}</p>
          <p v-else-if="!searching && !searchResults.length" class="result-empty">未找到匹配证据，尝试更具体的章节或概念名称。</p>
          <button
            v-for="item in searchResults.slice(0, 5)"
            :key="item.id || item.title"
            type="button"
            :class="{ selected: selectedSearchResult === item }"
            @click="openSearchResult(item)"
          >
            <span>{{ item.title || item.name }}</span><small>{{ Math.round(Number(item.score || item.relevance || 0) * 100) }}%</small>
          </button>
          <p v-if="selectedSearchResult" class="search-excerpt">{{ selectedSearchResult.excerpt || '该证据来自课程知识库。' }}</p>
        </section>

        <section class="detail-actions" aria-label="节点学习动作">
          <button type="button" :disabled="generatingExercise" @click="generateExercise">
            <LoaderCircle v-if="generatingExercise" class="spin" :size="15" />
            <ClipboardList v-else :size="15" />{{ generatingExercise ? '正在生成题库' : '生成练习' }}
          </button>
          <button type="button" :disabled="addingToPath" @click="addToPath">
            <LoaderCircle v-if="addingToPath" class="spin" :size="15" />
            <Sparkles v-else :size="15" />{{ addingToPath ? '正在加入' : '加入路径' }}
          </button>
        </section>
      </template>

      <div v-else class="detail-empty">
        <CircleDot :size="26" /><strong>选择一个知识节点</strong><p>查看掌握度、课程证据和可执行学习动作。</p>
      </div>
    </aside>

    <Transition name="toast">
      <div v-if="notice" class="toast-msg" role="status"><Check :size="15" />{{ notice }}</div>
    </Transition>
  </main>
</template>
