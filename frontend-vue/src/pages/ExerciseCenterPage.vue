<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { generatePathStageQuestions, getPathOverview, type PathOverview } from '@/api/learningApi'
import { useStudent } from '@/composables/useStudent'
import ExercisePage from '@/pages/ExercisePage.vue'
// @ts-ignore - local three package is installed without package metadata in this workspace.
import * as THREE from '../../node_modules/three/build/three.module.js'

type ResourceItem = {
  id: string
  type: string
  tags: string[]
  content_uri: string
  title?: string
  created_at?: string
  meta?: Record<string, any>
}

type WorkshopPageKey = 'builder' | 'wrongBook' | 'tagGalaxy' | 'diagnosis'
type ExercisePageExpose = {
  loadSession: (forceRefresh?: boolean) => Promise<boolean>
  resetForNewPaper: () => Promise<boolean>
  finishExam: () => Promise<boolean>
  hasActiveExam: () => boolean
}

const { studentId } = useStudent()
const route = useRoute()

function activeQuestionBankStorageKey(id: string) {
  return `exercise_active_question_banks:${id || 'anonymous'}`
}

function readActiveQuestionBankIds(id: string) {
  try {
    const raw = window.localStorage.getItem(activeQuestionBankStorageKey(id))
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.map(String).filter(Boolean) : []
  } catch {
    return []
  }
}

const majorCatalog = [
  { category: '工学', majors: ['计算机科学与技术', '软件工程', '人工智能', '数据科学与大数据技术', '网络工程', '信息安全', '物联网工程', '电子信息工程', '通信工程', '自动化', '电气工程及其自动化', '机械设计制造及其自动化', '车辆工程', '土木工程', '建筑学', '环境工程', '生物医学工程', '材料科学与工程', '化学工程与工艺', '航空航天工程', '其它'] },
  { category: '理学', majors: ['数学与应用数学', '信息与计算科学', '物理学', '应用物理学', '化学', '应用化学', '生物科学', '生物技术', '统计学', '应用统计学', '地理科学', '心理学', '应用心理学'] },
  { category: '经济学', majors: ['经济学', '金融学', '金融工程', '国际经济与贸易', '财政学', '税收学', '保险学', '投资学', '数字经济'] },
  { category: '管理学', majors: ['工商管理', '市场营销', '会计学', '财务管理', '人力资源管理', '审计学', '信息管理与信息系统', '工程管理', '物流管理', '电子商务', '旅游管理', '公共事业管理'] },
  { category: '文学', majors: ['汉语言文学', '汉语国际教育', '英语', '日语', '翻译', '新闻学', '传播学', '广告学', '网络与新媒体'] },
  { category: '法学', majors: ['法学', '知识产权', '政治学与行政学', '社会学', '社会工作', '思想政治教育'] },
  { category: '教育学', majors: ['教育学', '学前教育', '小学教育', '体育教育', '教育技术学', '特殊教育'] },
  { category: '医学', majors: ['临床医学', '口腔医学', '护理学', '药学', '中医学', '医学影像学', '医学检验技术', '公共卫生与预防医学'] },
  { category: '农学', majors: ['农学', '园艺', '植物保护', '动物科学', '动物医学', '林学', '水产养殖学'] },
  { category: '艺术学', majors: ['视觉传达设计', '环境设计', '产品设计', '数字媒体艺术', '音乐学', '舞蹈学', '广播电视编导', '动画'] },
  { category: '历史学', majors: ['历史学', '世界史', '考古学', '文物与博物馆学'] },
  { category: '哲学', majors: ['哲学', '逻辑学', '宗教学', '伦理学', '其它'] },
  { category: '其它', majors: ['其它'] },
]

const baseCourseCatalog = [
  { category: '公共基础课程', courses: ['高等数学', '线性代数', '概率论与数理统计', '大学物理', '大学英语', '程序设计基础', '大学计算机基础', '创新创业基础'] },
]

const professionalCourseCatalog: Record<string, { category: string; courses: string[] }[]> = {
  工学: [
    { category: '计算机与软件课程', courses: ['数据结构', '算法设计与分析', '操作系统', '计算机网络', '数据库系统原理', '软件工程', '软件需求分析与建模', '软件测试', '软件体系结构', '面向对象程序设计', 'Web 前端开发', 'Java 程序设计', 'Python 程序设计', '移动应用开发', '云计算与虚拟化', '机器学习', '深度学习', '自然语言处理', '计算机视觉', '信息安全基础', '密码学', '网络攻防实践', '大数据处理技术', '数据挖掘'] },
    { category: '电子信息与自动化课程', courses: ['电路分析', '模拟电子技术', '数字电子技术', '信号与系统', '通信原理', '数字信号处理', '自动控制原理', '现代控制理论', '嵌入式系统', '单片机原理', '传感器技术', '机器人学基础', 'PLC 控制技术'] },
    { category: '机械土木材料课程', courses: ['工程制图', '理论力学', '材料力学', '机械原理', '机械设计', '工程材料', '流体力学', '结构力学', '混凝土结构设计', '土力学', '建筑施工技术', '材料成型工艺'] },
  ],
  理学: [
    { category: '数学统计课程', courses: ['数学分析', '高等代数', '解析几何', '常微分方程', '复变函数', '实变函数', '数值分析', '概率论', '数理统计', '随机过程', '统计建模', '时间序列分析'] },
    { category: '物化生地课程', courses: ['力学', '电磁学', '热学', '光学', '量子力学', '无机化学', '有机化学', '分析化学', '物理化学', '普通生物学', '遗传学', '生态学', '自然地理学'] },
  ],
  经济学: [
    { category: '经济金融课程', courses: ['微观经济学', '宏观经济学', '计量经济学', '金融学', '公司金融', '投资学', '国际金融', '金融工程', '财政学', '产业经济学', '数字经济概论'] },
  ],
  管理学: [
    { category: '管理与商务课程', courses: ['管理学原理', '组织行为学', '市场营销', '会计学原理', '财务管理', '运营管理', '战略管理', '人力资源管理', '管理信息系统', '物流与供应链管理', '电子商务概论', '项目管理'] },
  ],
  文学: [
    { category: '语言传播课程', courses: ['现代汉语', '古代汉语', '中国古代文学', '中国现当代文学', '外国文学', '语言学概论', '英语写作', '翻译理论与实践', '新闻采访与写作', '传播学概论', '新媒体运营'] },
  ],
  法学: [
    { category: '法学与社会课程', courses: ['法理学', '宪法学', '民法', '刑法', '行政法', '商法', '经济法', '知识产权法', '国际法', '诉讼法', '社会学概论', '社会调查方法'] },
  ],
  教育学: [
    { category: '教育与心理课程', courses: ['教育学原理', '课程与教学论', '教育心理学', '发展心理学', '教育研究方法', '班级管理', '现代教育技术', '学习科学导论'] },
  ],
  医学: [
    { category: '医学与生命课程', courses: ['人体解剖学', '组织胚胎学', '生理学', '病理学', '药理学', '诊断学', '内科学', '外科学', '护理学基础', '生物化学', '分子生物学', '流行病学', '医学统计学'] },
  ],
  农学: [
    { category: '农林动物课程', courses: ['植物学', '植物生理学', '作物栽培学', '土壤肥料学', '植物保护学', '园艺学概论', '动物生理学', '动物营养学', '兽医基础', '林学概论'] },
  ],
  艺术学: [
    { category: '设计与艺术课程', courses: ['设计概论', '构成基础', '版式设计', '字体设计', '用户体验设计', '交互设计', '数字媒体技术', '动画分镜', '影视后期制作', '音乐基础', '艺术概论'] },
  ],
  历史学: [
    { category: '历史文化课程', courses: ['中国古代史', '中国近现代史', '世界古代史', '世界近现代史', '史学概论', '历史文献学', '考古学概论', '博物馆学基础'] },
  ],
  哲学: [
    { category: '哲学思维课程', courses: ['哲学导论', '中国哲学史', '西方哲学史', '逻辑学', '伦理学', '美学', '科学技术哲学', '宗教学概论'] },
  ],
  其它: [],
}

const practiceCourseCatalog = [
  { category: '电子信息与自动化课程', courses: ['电路分析', '模拟电子技术', '数字电子技术', '信号与系统', '通信原理', '自动控制原理', '嵌入式系统', '单片机原理', '传感器技术'] },
  { category: '实践与项目课程', courses: ['课程设计', '毕业设计', '专业实训', '创新实践项目', '软件项目管理', '企业真实项目实战', '竞赛专题训练'] },
]

const majorSpecificCourseCatalog: Record<string, { category: string; courses: string[] }[]> = {
  软件工程: [{ category: '软件工程专业课程', courses: ['软件需求分析与建模', '软件设计与体系结构', '软件项目管理', '软件测试与质量保证', '敏捷开发方法', 'DevOps 实践', '软件过程管理', 'UML 建模'] }],
  计算机科学与技术: [{ category: '计算机专业课程', courses: ['数据结构', '算法设计与分析', '计算机组成原理', '操作系统', '计算机网络', '编译原理', '数据库系统原理', '人工智能导论'] }],
  人工智能: [{ category: '人工智能专业课程', courses: ['机器学习', '深度学习', '自然语言处理', '计算机视觉', '知识图谱', '强化学习', '模式识别', '智能系统工程'] }],
  数据科学与大数据技术: [{ category: '数据科学专业课程', courses: ['数据采集与预处理', '大数据处理技术', '数据挖掘', '机器学习', '数据可视化', '分布式计算', '统计建模', '数据仓库与数据湖'] }],
  网络工程: [{ category: '网络工程专业课程', courses: ['计算机网络', '网络规划与设计', '路由交换技术', '网络协议分析', '网络安全', 'Linux 网络服务', '云网络技术', '网络运维自动化'] }],
  信息安全: [{ category: '信息安全专业课程', courses: ['密码学', '网络安全', 'Web 安全', '逆向工程', '安全协议分析', '渗透测试', '安全运维', '数字取证'] }],
  物联网工程: [{ category: '物联网专业课程', courses: ['物联网导论', '传感器技术', '嵌入式系统', '无线传感网络', 'RFID 原理与应用', '边缘计算', '物联网安全', '智能硬件开发'] }],
  电子信息工程: [{ category: '电子信息专业课程', courses: ['电路分析', '模拟电子技术', '数字电子技术', '信号与系统', '数字信号处理', '通信原理', 'EDA 技术', '嵌入式系统'] }],
  通信工程: [{ category: '通信工程专业课程', courses: ['通信原理', '信号与系统', '数字信号处理', '移动通信', '光纤通信', '通信网络', '信息论与编码', '无线通信技术'] }],
  自动化: [{ category: '自动化专业课程', courses: ['自动控制原理', '现代控制理论', '过程控制', '运动控制', 'PLC 控制技术', '传感器技术', '机器人学基础', '智能控制'] }],
  电气工程及其自动化: [{ category: '电气工程专业课程', courses: ['电路分析', '电机学', '电力电子技术', '电力系统分析', '继电保护', '高电压技术', '电气控制与 PLC', '新能源发电技术'] }],
  机械设计制造及其自动化: [{ category: '机械制造专业课程', courses: ['工程制图', '理论力学', '材料力学', '机械原理', '机械设计', '机械制造技术基础', '数控技术', '智能制造系统'] }],
  土木工程: [{ category: '土木工程专业课程', courses: ['材料力学', '结构力学', '土力学', '混凝土结构设计', '钢结构设计', '工程测量', '基础工程', '建筑施工技术'] }],
  建筑学: [{ category: '建筑学专业课程', courses: ['建筑设计基础', '建筑构造', '建筑物理', '城市设计', '建筑史', '建筑结构选型', '绿色建筑设计', '建筑设计专题'] }],
  环境工程: [{ category: '环境工程专业课程', courses: ['环境监测', '水污染控制工程', '大气污染控制工程', '固体废物处理', '环境影响评价', '环境微生物学', '环境工程原理'] }],
  材料科学与工程: [{ category: '材料专业课程', courses: ['材料科学基础', '材料物理性能', '材料力学性能', '金属材料学', '高分子材料', '材料分析测试方法', '材料成型工艺'] }],
  化学工程与工艺: [{ category: '化工专业课程', courses: ['化工原理', '化工热力学', '化学反应工程', '分离工程', '化工设计', '化工安全', '过程控制', '精细化工工艺'] }],
  数学与应用数学: [{ category: '数学专业课程', courses: ['数学分析', '高等代数', '解析几何', '常微分方程', '复变函数', '实变函数', '泛函分析', '数学建模'] }],
  统计学: [{ category: '统计学专业课程', courses: ['概率论', '数理统计', '回归分析', '多元统计分析', '时间序列分析', '统计计算', '抽样调查', '贝叶斯统计'] }],
  应用心理学: [{ category: '心理学专业课程', courses: ['普通心理学', '发展心理学', '教育心理学', '心理测量学', '实验心理学', '咨询心理学', '社会心理学', '认知心理学'] }],
  国际经济与贸易: [{ category: '国贸专业课程', courses: ['国际贸易理论', '国际贸易实务', '国际金融', '国际结算', '外贸函电', '跨境电商', '国际商法', '国际市场营销'] }],
  会计学: [{ category: '会计专业课程', courses: ['基础会计', '中级财务会计', '成本会计', '管理会计', '审计学', '税法', '财务报表分析', '会计信息系统'] }],
  金融学: [{ category: '金融专业课程', courses: ['金融学', '证券投资学', '公司金融', '商业银行经营管理', '金融风险管理', '国际金融', '金融市场学', '金融科技'] }],
  工商管理: [{ category: '工商管理专业课程', courses: ['管理学原理', '组织行为学', '战略管理', '运营管理', '市场营销', '人力资源管理', '公司治理', '创业管理'] }],
  市场营销: [{ category: '市场营销专业课程', courses: ['市场营销学', '消费者行为学', '市场调查', '品牌管理', '数字营销', '渠道管理', '服务营销', '营销策划'] }],
  汉语言文学: [{ category: '汉语言文学专业课程', courses: ['现代汉语', '古代汉语', '中国古代文学', '中国现当代文学', '文学理论', '比较文学', '写作学', '语言学概论'] }],
  英语: [{ category: '英语专业课程', courses: ['综合英语', '英语听力', '英语口语', '英语写作', '英汉翻译', '语言学概论', '英美文学', '跨文化交际'] }],
  新闻学: [{ category: '新闻传播专业课程', courses: ['新闻学概论', '新闻采访与写作', '新闻编辑', '传播学概论', '融合新闻', '舆论学', '数据新闻', '媒介经营管理'] }],
  法学: [{ category: '法学专业课程', courses: ['法理学', '宪法学', '民法', '刑法', '行政法', '商法', '经济法', '知识产权法', '国际法', '诉讼法'] }],
  学前教育: [{ category: '学前教育专业课程', courses: ['学前教育学', '学前心理学', '幼儿园课程', '儿童游戏理论', '幼儿卫生学', '幼儿行为观察', '幼儿园班级管理'] }],
  教育技术学: [{ category: '教育技术专业课程', courses: ['教学系统设计', '学习科学导论', '现代教育技术', '教育数据分析', '在线课程设计', '数字媒体技术', '智慧教育应用'] }],
  临床医学: [{ category: '临床医学专业课程', courses: ['人体解剖学', '生理学', '病理学', '药理学', '诊断学', '内科学', '外科学', '妇产科学', '儿科学'] }],
  护理学: [{ category: '护理专业课程', courses: ['护理学基础', '健康评估', '内科护理学', '外科护理学', '妇产科护理学', '儿科护理学', '急危重症护理学'] }],
  药学: [{ category: '药学专业课程', courses: ['药物化学', '药剂学', '药理学', '药物分析', '生药学', '临床药学', '药事管理学', '天然药物化学'] }],
  农学: [{ category: '农学专业课程', courses: ['植物学', '植物生理学', '作物栽培学', '作物育种学', '土壤肥料学', '植物保护学', '农业生态学'] }],
  视觉传达设计: [{ category: '视觉传达专业课程', courses: ['设计概论', '图形创意', '字体设计', '版式设计', '品牌视觉设计', '包装设计', '信息可视化设计', '用户体验设计'] }],
  数字媒体艺术: [{ category: '数字媒体艺术专业课程', courses: ['数字媒体技术', '交互设计', '动画分镜', '三维建模', '影视后期制作', '游戏设计基础', '用户体验设计', '动态图形设计'] }],
  历史学: [{ category: '历史学专业课程', courses: ['中国古代史', '中国近现代史', '世界古代史', '世界近现代史', '史学概论', '历史文献学', '史学论文写作'] }],
  哲学: [{ category: '哲学专业课程', courses: ['哲学导论', '中国哲学史', '西方哲学史', '逻辑学', '伦理学', '美学', '马克思主义哲学原理'] }],
}

const selectedMajorCategory = ref('工学')
const selectedMajor = ref('软件工程')
const customMajor = ref('')
const selectedCourseCategory = ref('软件工程专业课程')
const selectedCourse = ref('软件需求分析与建模')
const customCourseCategory = ref('')
const customCourse = ref('')
const activePage = ref<WorkshopPageKey>('builder')
const pendingPage = ref<WorkshopPageKey | null>(null)
const showExamLeaveDialog = ref(false)
const courseLocked = ref(false)
const exerciseResetSeed = ref(0)
const exercisePageRef = ref<ExercisePageExpose | null>(null)
const specificKnowledgePoint = ref('用例建模中的系统边界识别')
const knowledgePoint = ref('参与者识别、用例粒度、include/extend 关系、业务场景抽象')
const weaknessDetail = ref('不会区分用户目标和功能点，容易把按钮、页面、接口都写成用例。')
const specialRequirement = ref('题目尽量结合校园预约、在线选课、实验室管理等业务场景，案例题要能训练完整分析过程。')
const requirement = ref<Record<string, any> | null>(null)
const generating = ref(false)
const events = ref<any[]>([])
const resources = ref<ResourceItem[]>([])
const selectedQuestionBankIds = ref<string[]>(readActiveQuestionBankIds(studentId.value))
const error = ref('')
const closedLoopStatus = ref('题库生成后会自动进入训练诊断。')
const questionDifficulty = ref('mixed')
const activeExerciseQuestionLimit = ref(50)
const activeExerciseDifficulty = ref('mixed')
const questionTypeCounts = ref<Record<string, number>>({
  single_choice: 4,
  multiple_choice: 2,
  true_false: 2,
  blank: 0,
  short_answer: 1,
  case_analysis: 1,
  calculation: 0,
  matching: 0,
  ordering: 0,
})
const pathOverview = ref<PathOverview | null>(null)
const currentPathStage = ref<Record<string, any> | null>(null)
const pathContextLoading = ref(false)

const questionBankResources = computed(() => resources.value.filter((r) => r.type === 'question_bank'))
const activeQuestionBankIds = computed(() => selectedQuestionBankIds.value)
const requestedStageId = computed(() => String(route.query.stage || ''))
const requestedBankId = computed(() => String(route.query.bank || ''))
const shouldAutoStartStageBank = computed(() => String(route.query.autostart || '') === '1')
const pathCourseTitle = computed(() => pathOverview.value?.title || '当前学习路径')
const pathStageTitle = computed(() => String(currentPathStage.value?.title || '等待路径阶段'))
const pathStageGoal = computed(() => String(currentPathStage.value?.goal || currentPathStage.value?.checkpoint || '请先在路径推送中选择当前学习阶段。'))
const pathStageMastery = computed(() => Math.max(0, Math.min(100, Number(currentPathStage.value?.mastery) || 0)))
const pathStageProgressText = computed(() => {
  const answered = Number(currentPathStage.value?.answered_count) || 0
  const target = Number(currentPathStage.value?.target_count) || totalQuestionCount.value
  return `${answered} / ${Math.max(1, target)} 题`
})
const questionTypeOptions = [
  { value: 'single_choice', label: '单选题', hint: '概念辨析、基础判断' },
  { value: 'multiple_choice', label: '多选题', hint: '多条件识别、组合判断' },
  { value: 'true_false', label: '判断题', hint: '快速检测易错概念' },
  { value: 'blank', label: '填空题', hint: '关键词、定义、公式补全' },
  { value: 'short_answer', label: '简答题', hint: '步骤说明、原因分析' },
  { value: 'case_analysis', label: '案例分析', hint: '真实场景迁移应用' },
  { value: 'calculation', label: '计算题', hint: '公式推导、数值求解' },
  { value: 'matching', label: '匹配题', hint: '概念与解释配对' },
  { value: 'ordering', label: '排序题', hint: '流程、步骤、时序排序' },
]
const wrongBook = ref<any | null>(null)
const wrongBookLoading = ref(false)
const wrongBookError = ref('')
const galaxyRefreshing = ref(false)
const galaxyRefreshFeedback = ref('')
const selectedWrongRecordIds = ref<string[]>([])
const openCourseFolders = ref<Record<string, boolean>>({})
const exerciseRadarImpact = ref<Record<string, number>>({})
const galaxyCanvas = ref<HTMLCanvasElement | null>(null)
const activeGalaxyTag = ref('')
const galaxyAngle = ref(0)
const galaxyZoom = ref(1)
const galaxyInteractionStatus = ref('错题标签星系已就绪。')
const galaxyTargets = ref<{ tag: string; x: number; y: number; radius: number }[]>([])
const masteredGalaxyStars = ref<any[]>([])
const galaxyMouse = { x: 0, y: 0, targetX: 0, targetY: 0, active: false }
let galaxyFrame: number | null = null
let galaxyRenderer: any = null
let galaxyScene: any = null
let galaxyCamera: any = null
let galaxyRaycaster: any = null
let galaxyPointer: any = null
let galaxyCore: any = null
let galaxyDisk: any = null
let galaxyBackdrop: any = null
let galaxySkyDome: any = null
let galaxyAtmosphereLayers: any[] = []
let galaxyBackgroundSystems: any[] = []
let galaxyDeepField: any = null
let galaxyStarField: any = null
let galaxyDustField: any = null
let galaxyTrackGroup: any = null
let galaxyNebulae: any[] = []
let galaxyMasteredGroup: any = null
let galaxyNodeGroup: any = null
let galaxyLinkGroup: any = null
let galaxyNodeMeshes: any[] = []
let galaxyLinkMeshes: any[] = []
let galaxyNeedsRebuild = true
let galaxySceneSignature = ''
let galaxyRefreshVersion = 0
let galaxyRefreshFeedbackTimer: number | null = null
let galaxyReferenceTexture: any = null
let galaxyReferenceLoading = false
const galaxyTextureCache = new Map<string, any>()
const GALAXY_ZOOM_MIN = 0.62
const GALAXY_ZOOM_MAX = 1.9
const GALAXY_ZOOM_STEP = 0.08
const redoSession = ref<{
  scope: 'single' | 'course' | 'all'
  title: string
  queue: any[]
  index: number
  completed: boolean
  correct: number
  wrong: number
} | null>(null)
const redoAnswer = ref('')
const redoResult = ref<any | null>(null)
const totalQuestionCount = computed(() => {
  return questionTypeOptions.reduce((sum, option) => sum + normalizedTypeCount(option.value), 0)
})
const questionDifficultyLabel = computed(() => ({
  mixed: '由易到难混合',
  easy: '基础巩固',
  medium: '中等应用',
  hard: '综合提升',
}[questionDifficulty.value] || '自定义难度'))
const selectedQuestionTypes = computed(() => {
  const types = questionTypeOptions.map((option) => option.value).filter((type) => normalizedTypeCount(type) > 0)
  return types.length ? types : ['single_choice']
})
const majorOptions = computed(() => {
  const majors = majorCatalog.find((item) => item.category === selectedMajorCategory.value)?.majors || ['其它']
  return majors.includes('其它') ? majors : [...majors, '其它']
})
const courseCatalog = computed(() => {
  if (selectedMajor.value === '其它' || selectedMajorCategory.value === '其它') {
    return [{ category: '其它', courses: ['其它'] }]
  }
  const majorCourses = professionalCourseCatalog[selectedMajorCategory.value] || []
  const specificCourses = majorSpecificCourseCatalog[selectedMajor.value] || []
  return [...specificCourses, ...majorCourses, ...baseCourseCatalog, ...practiceCourseCatalog, { category: '其它', courses: ['其它'] }]
})
const courseOptions = computed(() => {
  const courses = courseCatalog.value.find((item) => item.category === selectedCourseCategory.value)?.courses || ['其它']
  return courses.includes('其它') ? courses : [...courses, '其它']
})
const effectiveMajor = computed(() => selectedMajor.value === '其它' ? customMajor.value.trim() || '自定义专业' : selectedMajor.value)
const effectiveCourseCategory = computed(() => selectedCourseCategory.value === '其它' ? customCourseCategory.value.trim() || '自定义课程类别' : selectedCourseCategory.value)
const effectiveCourse = computed(() => selectedCourse.value === '其它' ? customCourse.value.trim() || '自定义课程内容' : selectedCourse.value)
const abilityRadar = computed(() => {
  const rawValues = wrongBook.value?.ability_radar || []
  const values = rawValues.length ? rawValues : [
    { name: '基础知识掌握能力', score: 0, total: 0 },
    { name: '逻辑思维', score: 0, total: 0 },
    { name: '运算处理能力', score: 0, total: 0 },
    { name: '抽象概括能力', score: 0, total: 0 },
    { name: '应用迁移能力', score: 0, total: 0 },
    { name: '错因复盘能力', score: 0, total: 0 },
  ]
  const impacts = exerciseRadarImpact.value
  return values.map((item: any) => {
    const delta = Number(impacts[item.name] || 0)
    const score = Math.max(0, Math.min(100, Number(item.score ?? 0) + delta))
    return { ...item, score, training_delta: delta }
  })
})
const radarPoints = computed(() => abilityRadar.value.map((item: any, index: number) => radarPoint(index, Number(item.score) || 0)).join(' '))
const radarOldPoints = computed(() => abilityRadar.value.map((item: any, index: number) => radarPoint(index, Number(item.old_score ?? 0) || 0)).join(' '))
const radarSignature = computed(() => `${wrongBookStats.value.totalWrong}-${wrongBookStats.value.tagCount}-${radarOldPoints.value}-${radarPoints.value}`)
const currentRedoRecord = computed(() => redoSession.value?.queue[redoSession.value.index] || null)
const currentRedoIsMultiple = computed(() => isMultipleQuestion(currentRedoRecord.value))
const redoOptions = computed(() => {
  const record = currentRedoRecord.value
  const options = normalizeOptions(record?.options || [])
  if (!options.length && record?.stem) {
    const stemOptions = normalizeOptions([record.stem])
    if (stemOptions.length > 1) return stemOptions
  }
  if (!options.length && record?.type === 'true_false') return normalizeOptions(['A. 正确', 'B. 错误'])
  return options
})
const wrongBookStats = computed(() => {
  const groups = wrongBook.value?.groups || []
  const courseCount = groups.reduce((sum: number, group: any) => sum + (group.courses?.length || 0), 0)
  const totalWrong = groups.reduce((sum: number, group: any) => sum + (Number(group.count) || 0), 0)
  return {
    totalWrong,
    courseCount,
    tagCount: wrongBook.value?.tag_summary?.length || 0,
  }
})
const courseFolders = computed(() => {
  return (wrongBook.value?.groups || []).flatMap((major: any) =>
    (major.courses || []).map((course: any) => ({
      major: major.major,
      course: course.course,
      count: course.count,
      items: course.items || [],
      key: folderKey(major.major, course.course),
    }))
  )
})
const allCourseFoldersOpen = computed(() => {
  return !!courseFolders.value.length && courseFolders.value.every((folder: any) => openCourseFolders.value[folder.key])
})
const selectedWrongRecords = computed(() => {
  const ids = new Set(selectedWrongRecordIds.value)
  return (wrongBook.value?.records || []).filter((record: any) => ids.has(String(record.id)))
})
const redoAllButtonText = computed(() => selectedWrongRecords.value.length ? `重做已选 ${selectedWrongRecords.value.length} 题` : '一键重做')
const tagGalaxy = computed(() => {
  const records = wrongBook.value?.records || []
  const nodeMap = new Map<string, any>()
  const linkMap = new Map<string, any>()
  const clusterMap = new Map<string, number>()

  for (const record of records) {
    const tags = Array.isArray(record.tags) ? record.tags.map((tag: any) => String(tag).trim()).filter(Boolean) : []
    const major = String(record.major || effectiveMajor.value || '通用能力')
    const course = String(record.course || effectiveCourse.value || '综合练习')
    const knowledge = String(record.knowledge_point || record.chapter || '综合知识点')
    const clusterKey = `${major} / ${course}`
    if (!clusterMap.has(clusterKey)) clusterMap.set(clusterKey, clusterMap.size)

    for (const tag of tags) {
      const node = nodeMap.get(tag) || {
        tag,
        count: 0,
        major,
        course,
        knowledge,
        clusterKey,
        courses: new Set<string>(),
        points: new Set<string>(),
      }
      node.count += 1
      node.courses.add(course)
      node.points.add(knowledge)
      nodeMap.set(tag, node)
    }

    for (let i = 0; i < tags.length; i += 1) {
      for (let j = i + 1; j < tags.length; j += 1) {
        const [a, b] = [tags[i], tags[j]].sort()
        const key = `${a}::${b}`
        const link = linkMap.get(key) || { source: a, target: b, weight: 0, reason: clusterKey }
        link.weight += 2
        linkMap.set(key, link)
      }
    }
  }

  const rawLinks = Array.from(linkMap.values())
  const activeTag = activeGalaxyTag.value
  const relatedEntries = activeTag
    ? rawLinks
        .filter((link: any) => link.source === activeTag || link.target === activeTag)
        .map((link: any) => ({
          tag: link.source === activeTag ? link.target : link.source,
          weight: Number(link.weight) || 1,
        }))
        .sort((a, b) => b.weight - a.weight || a.tag.localeCompare(b.tag))
    : []
  const relatedOrder = new Map(relatedEntries.map((item, index) => [item.tag, { ...item, index }]))
  const maxRelatedWeight = Math.max(1, ...relatedEntries.map((item) => item.weight))
  const clusters = Math.max(1, clusterMap.size)
  const nodes = Array.from(nodeMap.values()).map((node: any, index) => {
    const clusterIndex = clusterMap.get(node.clusterKey) || 0
    const clusterAngle = (Math.PI * 2 * clusterIndex) / clusters
    const orbit = 88 + Math.min(70, node.count * 12)
    const drift = (hashText(node.tag) % 100) / 100
    const local = (index * 0.72 + drift * 2.4) % (Math.PI * 2)
    const hue = (clusterIndex * 61 + 206) % 360
    const relation = relatedOrder.get(node.tag)
    const focusMode = Boolean(activeTag)
    const isCenter = activeTag === node.tag
    const isRelated = Boolean(relation)
    const relationIndex = relation?.index ?? index
    const relationWeight = relation?.weight ?? 0
    const focusAngle = relationIndex * 2.399963 + drift * 0.5
    const focusOrbit = isCenter
      ? 0
      : isRelated
        ? 78 + (relationIndex % 3) * 34 + (maxRelatedWeight - relationWeight) * 9
        : 220 + (index % 4) * 36
    const focusY = isCenter
      ? 0
      : isRelated
        ? Math.sin(focusAngle * 1.4) * 48
        : Math.sin(local * 1.3) * 84
    return {
      ...node,
      x: focusMode ? Math.cos(focusAngle) * focusOrbit : Math.cos(clusterAngle) * orbit + Math.cos(local) * 36,
      y: focusMode ? focusY : Math.sin(local * 1.3) * 58,
      z: focusMode ? Math.sin(focusAngle) * focusOrbit : Math.sin(clusterAngle) * orbit + Math.sin(local) * 36,
      hue,
      color: `hsl(${hue} 82% 56%)`,
      focusMode,
      isCenter,
      isRelated,
      relationWeight,
      orbitRadius: focusOrbit,
      orbitPhase: focusAngle,
      orbitSpeed: isRelated ? 0.35 + (relationIndex % 5) * 0.08 : 0.16,
      courses: Array.from(node.courses),
      points: Array.from(node.points),
    }
  })
  const nodeSet = new Set(nodes.map((node: any) => node.tag))
  const links = rawLinks.filter((link: any) => nodeSet.has(link.source) && nodeSet.has(link.target))
  return { nodes, links, clusters: Array.from(clusterMap.keys()) }
})

function syncMajorCategory() {
  selectedMajor.value = majorOptions.value[0] || ''
  syncCourseCatalog()
  syncCustomizationDefaults()
}

function syncMajor() {
  syncCourseCatalog()
  syncCustomizationDefaults()
}

function syncCourseCatalog() {
  selectedCourseCategory.value = courseCatalog.value[0]?.category || '其它'
  selectedCourse.value = courseOptions.value[0] || ''
  syncCustomizationDefaults()
}

function syncCourse() {
  selectedCourse.value = courseOptions.value[0] || ''
  syncCustomizationDefaults()
}

function syncCustomizationDefaults() {
  const course = effectiveCourse.value
  const major = effectiveMajor.value
  const presets: Record<string, { point: string; range: string; weakness: string; special: string }> = {
    软件需求分析与建模: {
      point: '用例建模中的系统边界识别',
      range: '参与者识别、用例粒度、include/extend 关系、业务场景抽象',
      weakness: '不会区分用户目标和功能点，容易把按钮、页面、接口都写成用例。',
      special: '题目尽量结合校园预约、在线选课、实验室管理等业务场景，案例题要能训练完整分析过程。',
    },
    数据结构: {
      point: '链表、栈、队列与树结构的适用场景判断',
      range: '时间复杂度、空间复杂度、递归、遍历、查找与排序',
      weakness: '容易只记住结构定义，不会根据题目场景判断应该选哪种数据结构。',
      special: '增加代码阅读题和复杂度分析题，题目要覆盖基础概念到应用迁移。',
    },
    计算机网络: {
      point: 'TCP/IP 分层模型与可靠传输机制',
      range: '三次握手、四次挥手、拥塞控制、HTTP、DNS、网络安全基础',
      weakness: '容易混淆不同协议所在层级，不会解释协议机制背后的原因。',
      special: '增加协议流程排序题和网络故障排查案例题。',
    },
    机器学习: {
      point: '监督学习模型选择与过拟合判断',
      range: '训练集/测试集、损失函数、正则化、评估指标、交叉验证',
      weakness: '能记住算法名称，但不会根据数据特征选择模型和解释评估指标。',
      special: '增加指标计算题和真实业务分类场景案例题。',
    },
    会计学原理: {
      point: '借贷记账法与会计分录编制',
      range: '会计要素、账户结构、试算平衡、凭证与账簿',
      weakness: '容易判断错借贷方向，对经济业务和会计科目的对应关系不稳定。',
      special: '增加经济业务场景题和分录纠错题。',
    },
    民法: {
      point: '民事法律关系与合同效力判断',
      range: '主体、客体、意思表示、代理、违约责任、侵权责任',
      weakness: '读案例时容易漏掉关键事实，不能稳定提取法律关系。',
      special: '增加案例分析题，要求按事实、争点、规则、结论展开。',
    },
  }
  const preset = presets[course] || {
    point: `${course}的核心概念与典型应用`,
    range: `${course}的基础概念、关键流程、常见误区、综合应用`,
    weakness: `我想针对${major}专业中${course}的易混概念和应用题进行训练。`,
    special: '题目需要从基础理解逐步过渡到综合应用，并给出适合比赛录屏展示的诊断闭环。',
  }
  specificKnowledgePoint.value = preset.point
  knowledgePoint.value = preset.range
  weaknessDetail.value = preset.weakness
  specialRequirement.value = preset.special
}

function doClarify() {
  error.value = ''
  const dialogueRequirement = [
    `具体知识点：${specificKnowledgePoint.value}`,
    `关联知识范围：${knowledgePoint.value}`,
    `薄弱点：${weaknessDetail.value}`,
    `特殊定制需求：${specialRequirement.value}`,
  ].filter((item) => !item.endsWith('：')).join('\n')
  const weakPoints = extractWeakPoints(weaknessDetail.value || dialogueRequirement)
  requirement.value = {
    major_category: selectedMajorCategory.value,
    major: effectiveMajor.value,
    course_category: effectiveCourseCategory.value,
    course: effectiveCourse.value,
    chapter: specificKnowledgePoint.value || effectiveCourse.value,
    specific_knowledge_point: specificKnowledgePoint.value,
    knowledge_points: knowledgePoint.value,
    goals: dialogueRequirement,
    weak_points: weakPoints,
    special_requirements: specialRequirement.value,
    preferred_resources: ['question_bank'],
    constraints: { source: 'major_course_dialogue', difficulty: questionDifficulty.value },
    dialogue_requirement: dialogueRequirement,
  }
  applyQuizConfig()
  closedLoopStatus.value = '已根据专业、课程和对话内容生成题库需求。'
  activePage.value = 'builder'
}

function extractWeakPoints(text: string) {
  const patterns = ['不懂', '不会', '不理解', '没听懂', '搞不清', '混淆', '容易错', '短板是', '薄弱点是', '卡在']
  const items: string[] = []
  for (const part of text.split(/[。；;\n]/)) {
    if (patterns.some((p) => part.includes(p))) items.push(part.trim())
  }
  return items.length ? items.slice(0, 6) : [text.slice(0, 80)]
}

function setActiveQuestionBankIds(ids: string[]) {
  selectedQuestionBankIds.value = [...new Set(ids.map(String).filter(Boolean))]
  try {
    window.localStorage.setItem(
      activeQuestionBankStorageKey(studentId.value),
      JSON.stringify(selectedQuestionBankIds.value),
    )
  } catch {
    // localStorage 不可用时仍可在当前页面使用生成题库。
  }
}

function applyActiveQuestionBankConfig(banks: ResourceItem[]) {
  const configs = banks
    .map((bank) => bank.meta?.requirement?.question_config || bank.meta?.question_config || null)
    .filter((config) => config && typeof config === 'object')
  const configuredCount = configs.reduce((sum, config) => sum + Math.max(0, Number(config.count) || 0), 0)
  activeExerciseQuestionLimit.value = configuredCount ? Math.max(1, Math.min(50, configuredCount)) : 50
  activeExerciseDifficulty.value = String(configs[configs.length - 1]?.difficulty || 'mixed')
}

async function loadPathContext() {
  pathContextLoading.value = true
  try {
    const data = await getPathOverview(studentId.value)
    pathOverview.value = data
    const requested = (data.nodes || []).find((node: any) => String(node.id || '') === requestedStageId.value)
    const fallback = data.current_stage || (data.nodes || []).find((node: any) => ['current', 'active', 'warning'].includes(String(node.status)))
    const stage = requested && requested.status !== 'locked' ? requested : fallback
    currentPathStage.value = stage || null
    if (!stage) {
      error.value = '当前没有可用的学习阶段，请先到路径推送生成学习路径。'
      activePage.value = 'builder'
      return
    }
    specificKnowledgePoint.value = String(stage.title || '')
    knowledgePoint.value = String(stage.goal || stage.checkpoint || '')
    weaknessDetail.value = `围绕路径节点“${stage.title || '当前阶段'}”检测掌握情况。`
    specialRequirement.value = '题目仅覆盖当前路径阶段，完成后自动更新掌握度并判定是否进入下一阶段。'
    const target = Number(stage.target_count) || 0
    if (target) activeExerciseQuestionLimit.value = Math.max(1, Math.min(50, target))
  } catch (reason: any) {
    error.value = reason?.message || '当前路径阶段加载失败'
    currentPathStage.value = null
    activePage.value = 'builder'
  } finally {
    pathContextLoading.value = false
  }
}

async function restoreActiveQuestionBanks() {
  try {
    const resp = await fetch(`/api/resources?student_id=${encodeURIComponent(studentId.value)}`)
    if (!resp.ok) return
    const payload = await resp.json()
    if (!payload?.success) return
    const banks = (payload.data?.resources || []).filter((resource: ResourceItem) => (
      resource.type === 'question_bank'
      && resource.id
      && resource.meta?.requirement?.constraints?.source === 'path_stage_quiz'
      && String(resource.meta?.requirement?.constraints?.path_stage_id || '') === String(currentPathStage.value?.id || '')
    ))
    resources.value = banks
    if (!banks.length) {
      setActiveQuestionBankIds([])
      activeExerciseQuestionLimit.value = Math.max(1, Math.min(50, totalQuestionCount.value || 10))
      activeExerciseDifficulty.value = 'mixed'
      activePage.value = 'builder'
      return
    }
    const orderedBanks = [...banks].sort((left: ResourceItem, right: ResourceItem) => {
      const leftTime = Date.parse(left.created_at || '') || 0
      const rightTime = Date.parse(right.created_at || '') || 0
      return leftTime - rightTime
    })
    const latestBank = orderedBanks[orderedBanks.length - 1]
    const availableIds = new Set(banks.map((resource: ResourceItem) => String(resource.id)))
    const stageBankIds = Array.isArray(currentPathStage.value?.question_bank_ids)
      ? currentPathStage.value!.question_bank_ids.map(String).filter((id: string) => availableIds.has(id))
      : []
    const preferredId = availableIds.has(requestedBankId.value)
      ? requestedBankId.value
      : String(currentPathStage.value?.active_question_bank_id || latestBank.id)
    const restoredIds = preferredId && availableIds.has(preferredId)
      ? [preferredId]
      : stageBankIds.length ? [stageBankIds[stageBankIds.length - 1]] : [latestBank.id]
    setActiveQuestionBankIds(restoredIds)
    applyActiveQuestionBankConfig(banks.filter((bank: ResourceItem) => restoredIds.includes(String(bank.id))))
    activePage.value = 'diagnosis'
  } catch {
    setActiveQuestionBankIds([])
  }
}

async function doGenerate(): Promise<boolean> {
  if (!requirement.value || generating.value) return false
  applyQuizConfig()
  events.value = []
  resources.value = []
  generating.value = true
  error.value = ''
  closedLoopStatus.value = '正在根据专业、课程和学习短板生成个性化题库...'
  const generatedQuestionBankIds: string[] = []

  const consumeChunk = (chunk: string) => {
    const line = chunk.split('\n').find((item) => item.startsWith('data: '))
    if (!line) return
    try {
      const data = JSON.parse(line.slice(6))
      if (data?.error) {
        error.value = String(data.error)
        return
      }
      const evt = data.event
      if (!evt) return
      events.value.push(evt)
      if (evt.type === 'agent_done' && evt.resource) {
        const resource = evt.resource as ResourceItem
        resources.value.unshift(resource)
        if (resource.type === 'question_bank' && resource.id && !generatedQuestionBankIds.includes(resource.id)) {
          generatedQuestionBankIds.push(resource.id)
        }
      }
    } catch {
      // 忽略不完整 SSE 片段。
    }
  }

  try {
    const resp = await fetch('/api/exercise/generate-bank', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ student_id: studentId.value, requirement: requirement.value, stream: true }),
    })

    if (!resp.ok || !resp.body) throw new Error('流式生成连接失败')

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop() || ''
      for (const chunk of parts) consumeChunk(chunk)
    }
    buf += decoder.decode()
    if (buf.trim()) consumeChunk(buf)

    if (!generatedQuestionBankIds.length) {
      error.value = error.value || '生成流程没有返回可用题库，请重新生成。'
      return false
    }
    applyActiveQuestionBankConfig(questionBankResources.value.filter((bank) => generatedQuestionBankIds.includes(bank.id)))
    setActiveQuestionBankIds(generatedQuestionBankIds)
    return true
  } catch (e: any) {
    error.value = e?.message || '题库生成服务连接失败'
    return false
  } finally {
    generating.value = false
  }
}

function applyQuizConfig() {
  if (!requirement.value) return
  const typeCounts = Object.fromEntries(
    questionTypeOptions
      .map((option) => [option.value, normalizedTypeCount(option.value)])
      .filter(([, count]) => Number(count) > 0)
  )
  requirement.value = {
    ...(requirement.value || {}),
    question_config: {
      count: Math.max(1, Math.min(50, totalQuestionCount.value || 1)),
      difficulty: questionDifficulty.value,
      types: selectedQuestionTypes.value,
      type_counts: typeCounts,
    },
  }
}

function normalizedTypeCount(type: string) {
  return Math.max(0, Math.min(20, Number(questionTypeCounts.value[type]) || 0))
}

function goCustomize() {
  courseLocked.value = true
  doClarify()
  activePage.value = 'builder'
}

function resetCourseWorkflow() {
  courseLocked.value = false
  selectedMajorCategory.value = '工学'
  activePage.value = 'builder'
  pendingPage.value = null
  showExamLeaveDialog.value = false
  requirement.value = null
  events.value = []
  resources.value = []
  error.value = ''
  closedLoopStatus.value = '已重新开始专业课程选择，错题本数据已保留。'
  redoSession.value = null
  redoAnswer.value = ''
  redoResult.value = null
  selectedWrongRecordIds.value = []
  exerciseResetSeed.value += 1
  syncMajorCategory()
}

async function generateFromCustomize() {
  if (!currentPathStage.value || generating.value || totalQuestionCount.value <= 0) return
  generating.value = true
  error.value = ''
  closedLoopStatus.value = `正在为路径阶段“${pathStageTitle.value}”生成专属题库...`
  const typeCounts = Object.fromEntries(
    questionTypeOptions
      .map((option) => [option.value, normalizedTypeCount(option.value)])
      .filter(([, count]) => Number(count) > 0),
  )
  try {
    const data = await generatePathStageQuestions(studentId.value, {
      stageId: String(currentPathStage.value.id || ''),
      difficulty: questionDifficulty.value as 'mixed' | 'easy' | 'medium' | 'hard',
      count: Math.max(1, Math.min(50, totalQuestionCount.value)),
      questionTypes: selectedQuestionTypes.value,
      typeCounts,
    })
    const bank = data?.question_bank as ResourceItem | undefined
    if (!bank?.id) throw new Error('题库模型没有返回可用题库')
    resources.value = Array.isArray(data?.resources) ? data.resources : [bank]
    currentPathStage.value = data?.stage || currentPathStage.value
    setActiveQuestionBankIds([bank.id])
    activeExerciseQuestionLimit.value = Math.max(1, Math.min(50, Number(data?.stage?.target_count) || totalQuestionCount.value))
    activeExerciseDifficulty.value = questionDifficulty.value
    closedLoopStatus.value = `已载入“${pathStageTitle.value}”专属题库；每次提交都会更新阶段掌握度，达到 80% 后自动进入下一阶段。`
    activePage.value = 'diagnosis'
    exerciseResetSeed.value += 1
    await nextTick()
    await exercisePageRef.value?.loadSession?.(true)
  } catch (reason: any) {
    error.value = reason?.message || '阶段题库生成失败'
    closedLoopStatus.value = '阶段题库尚未生成，请检查模型配置后重试。'
  } finally {
    generating.value = false
  }
}

async function refreshExerciseLoop() {
  closedLoopStatus.value = activeQuestionBankIds.value.length
    ? `已同步 ${activeQuestionBankIds.value.length} 份个性化题库，可在智能做题中开始练习。`
    : '当前阶段还没有题库，请先在题库定制中选择难度、数量和题型。'
  await nextTick()
}

function emptyWrongBookData() {
  return {
    groups: [],
    records: [],
    ability_radar: [],
    tag_summary: [],
    stats: { total: 0, correct: 0, wrong: 0, accuracy: 0, weak_tags: [], corrections: [] },
  }
}

function masteredGalaxyStorageKey() {
  return `workshop_mastered_galaxy_stars:${studentId.value}`
}

function loadMasteredGalaxyStars() {
  try {
    const raw = window.localStorage.getItem(masteredGalaxyStorageKey())
    const parsed = raw ? JSON.parse(raw) : []
    masteredGalaxyStars.value = Array.isArray(parsed) ? parsed.slice(0, 120) : []
  } catch {
    masteredGalaxyStars.value = []
  }
}

function saveMasteredGalaxyStars() {
  try {
    window.localStorage.setItem(masteredGalaxyStorageKey(), JSON.stringify(masteredGalaxyStars.value.slice(0, 120)))
  } catch {
  }
}

function recordMasteredGalaxyStar(record: any) {
  const tags = Array.isArray(record?.tags) ? record.tags.map((tag: any) => String(tag).trim()).filter(Boolean) : []
  const tag = tags[0] || String(record?.tag || record?.knowledge_point || '已掌握错题')
  const id = `${record?.id || record?.question_id || tag}-${Date.now()}`
  masteredGalaxyStars.value = [
    {
      id,
      tag,
      tags,
      major: record?.major || effectiveMajor.value,
      course: record?.course || effectiveCourse.value,
      point: record?.knowledge_point || record?.chapter || '错题重做正确',
      created_at: Date.now(),
      hue: 42 + (hashText(id) % 62),
    },
    ...masteredGalaxyStars.value,
  ].slice(0, 120)
  saveMasteredGalaxyStars()
  galaxyNeedsRebuild = true
}

function applyExerciseRadarImpact(payload: any) {
  const question = payload?.question || {}
  const text = `${question.type || ''} ${(question.tags || []).join(' ')} ${question.stem || ''}`
  const correct = Boolean(payload?.correct)
  const baseDelta = correct ? 0.9 : -1.15
  const next = { ...exerciseRadarImpact.value }
  const names = abilityRadar.value.map((item: any) => String(item.name))
  for (const name of names) {
    let weight = 0.34
    if (/基础|知识|概念/.test(name) && /概念|基础|判断|填空|定义/.test(text)) weight = 1
    if (/逻辑/.test(name) && /逻辑|推理|关系|选择|多选/.test(text)) weight = 1
    if (/运算|处理/.test(name) && /计算|公式|数值|运算/.test(text)) weight = 1
    if (/抽象|概括/.test(name) && /建模|抽象|UML|用例|结构|设计/.test(text)) weight = 1
    if (/应用|迁移/.test(name) && /案例|场景|应用|项目|业务/.test(text)) weight = 1
    if (/错因|复盘/.test(name)) weight = correct ? 0.8 : 1
    const current = Number(next[name] || 0)
    next[name] = Math.max(-18, Math.min(18, Number((current + baseDelta * weight).toFixed(2))))
  }
  exerciseRadarImpact.value = next
}

async function loadWrongBook() {
  wrongBookLoading.value = true
  wrongBookError.value = ''
  try {
    const resp = await fetch(`/api/exercise/wrong-book?student_id=${encodeURIComponent(studentId.value)}`)
    if (!resp.ok) throw new Error('错题本服务暂不可用')
    const payload = await resp.json()
    if (payload.success) {
      wrongBook.value = payload.data || emptyWrongBookData()
      // The persisted summary is authoritative after every answer; clear the
      // optimistic delta so the same answer is not counted twice.
      exerciseRadarImpact.value = {}
      const liveIds = new Set((wrongBook.value.records || []).map((record: any) => String(record.id)))
      selectedWrongRecordIds.value = selectedWrongRecordIds.value.filter((id) => liveIds.has(String(id)))
      await nextTick()
      if (courseFolders.value.length && !Object.values(openCourseFolders.value).some(Boolean)) {
        const first = courseFolders.value[0]
        openCourseFolders.value = { [first.key]: true }
      }
      return true
    } else {
      throw new Error(payload.error?.message || '错题本数据加载失败')
    }
  } catch (e: any) {
    if (!wrongBook.value) wrongBook.value = emptyWrongBookData()
    wrongBookError.value = e?.message || '错题本服务暂不可用'
    return false
  } finally {
    wrongBookLoading.value = false
  }
}

function switchDirect(page: WorkshopPageKey) {
  activePage.value = page
}

function trySwitchPage(page: WorkshopPageKey) {
  if (page === activePage.value) return
  if (activePage.value === 'diagnosis' && page !== 'diagnosis' && exercisePageRef.value?.hasActiveExam?.()) {
    pendingPage.value = page
    showExamLeaveDialog.value = true
    return
  }
  switchDirect(page)
}

async function confirmSubmitExamAndLeave() {
  const target = pendingPage.value
  const submitted = await exercisePageRef.value?.finishExam?.()
  if (!submitted) return
  showExamLeaveDialog.value = false
  pendingPage.value = null
  if (target) switchDirect(target)
}

function cancelSubmitExamAndLeave() {
  showExamLeaveDialog.value = false
  pendingPage.value = null
}

function folderKey(major: string, course: string) {
  return `${major}::${course}`
}

function toggleCourseFolder(major: string, course: string) {
  const key = folderKey(major, course)
  openCourseFolders.value = {
    ...openCourseFolders.value,
    [key]: !openCourseFolders.value[key],
  }
}

function showAllCourseFolders() {
  openCourseFolders.value = Object.fromEntries(courseFolders.value.map((folder: any) => [folder.key, true]))
}

function hideAllCourseFolders() {
  openCourseFolders.value = {}
}

function toggleAllCourseFolders() {
  if (allCourseFoldersOpen.value) hideAllCourseFolders()
  else showAllCourseFolders()
}

function startRedoSession(scope: 'single' | 'course' | 'all', records: any[], title: string) {
  const seen = new Set<string>()
  const queue = records.filter((record) => {
    const key = recordKey(record)
    if (!record?.question_id || seen.has(key)) return false
    seen.add(key)
    return true
  })
  if (!queue.length) return
  redoSession.value = {
    scope,
    title,
    queue,
    index: 0,
    completed: false,
    correct: 0,
    wrong: 0,
  }
  redoAnswer.value = ''
  redoResult.value = null
}

function openRedo(record: any) {
  startRedoSession('single', [record], '重做本题')
}

function openRedoCourse(major: any, course: any) {
  startRedoSession('course', course.items || [], `${major.major} / ${course.course}`)
}

function openRedoAll() {
  const picked = selectedWrongRecords.value.length ? selectedWrongRecords.value : wrongBook.value?.records || []
  startRedoSession('all', picked, selectedWrongRecords.value.length ? '已选错题重做' : '全部错题重做')
}

function openTagGalaxy(tag = '') {
  activeGalaxyTag.value = tag
  trySwitchPage('tagGalaxy')
}

async function refreshTagGalaxy() {
  if (galaxyRefreshing.value) return
  galaxyRefreshing.value = true
  galaxyRefreshFeedback.value = ''
  if (galaxyRefreshFeedbackTimer !== null) {
    window.clearTimeout(galaxyRefreshFeedbackTimer)
    galaxyRefreshFeedbackTimer = null
  }

  const loaded = await loadWrongBook()
  if (loaded && activePage.value === 'tagGalaxy') {
    galaxyRefreshVersion += 1
    galaxySceneSignature = ''
    galaxyNeedsRebuild = true
    galaxyAngle.value = 0
    galaxyZoom.value = 1
    Object.assign(galaxyMouse, { x: 0, y: 0, targetX: 0, targetY: 0, active: false })
    await nextTick()
    startTagGalaxy()
    galaxyRefreshFeedback.value = '已刷新'
  } else {
    galaxyRefreshFeedback.value = '刷新失败'
  }

  galaxyRefreshing.value = false
  galaxyRefreshFeedbackTimer = window.setTimeout(() => {
    galaxyRefreshFeedback.value = ''
    galaxyRefreshFeedbackTimer = null
  }, 1800)
}

function hashText(text: string) {
  let hash = 0
  for (let i = 0; i < text.length; i += 1) hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0
  return Math.abs(hash)
}

function startTagGalaxy() {
  stopTagGalaxy()
  const nextSignature = [
    tagGalaxy.value.nodes.map((node: any) => `${node.tag}:${node.count}`).join('|'),
    tagGalaxy.value.links.map((link: any) => `${link.source}-${link.target}:${link.weight}`).join('|'),
    masteredGalaxyStars.value.map((item: any) => item.id).join('|'),
    `refresh:${galaxyRefreshVersion}`,
  ].join('::')
  if (nextSignature !== galaxySceneSignature || !galaxyScene || !galaxyCamera) {
    galaxySceneSignature = nextSignature
    galaxyNeedsRebuild = true
  } else {
    refreshGalaxyFocusState()
  }
  animateTagGalaxy()
}

function stopTagGalaxy() {
  if (galaxyFrame !== null) {
    window.cancelAnimationFrame(galaxyFrame)
    galaxyFrame = null
  }
}

function disposeGalaxyObject(item: any, disposeMap = true) {
  if (!item) return
  item.traverse?.((child: any) => {
    child.geometry?.dispose?.()
    if (Array.isArray(child.material)) {
      child.material.forEach((material: any) => {
        if (disposeMap) material.map?.dispose?.()
        material.dispose?.()
      })
    } else if (child.material) {
      if (disposeMap) child.material.map?.dispose?.()
      child.material.dispose?.()
    }
  })
  if (!item.traverse) {
    item.geometry?.dispose?.()
    if (disposeMap) item.material?.map?.dispose?.()
    item.material?.dispose?.()
  }
}

function disposeTagGalaxyScene() {
  for (const item of [...galaxyNodeMeshes, ...galaxyLinkMeshes, ...galaxyNebulae, ...galaxyAtmosphereLayers, ...galaxyBackgroundSystems, galaxyCore, galaxyDisk, galaxySkyDome, galaxyDeepField, galaxyStarField, galaxyDustField, galaxyTrackGroup, galaxyMasteredGroup]) disposeGalaxyObject(item, false)
  disposeGalaxyObject(galaxyBackdrop, false)
  galaxyNodeMeshes = []
  galaxyLinkMeshes = []
  galaxyNebulae = []
  galaxyScene?.clear?.()
  galaxyScene = null
  galaxyCamera = null
  galaxyRaycaster = null
  galaxyPointer = null
  galaxyCore = null
  galaxyDisk = null
  galaxyBackdrop = null
  galaxySkyDome = null
  galaxyAtmosphereLayers = []
  galaxyBackgroundSystems = []
  galaxyDeepField = null
  galaxyStarField = null
  galaxyDustField = null
  galaxyTrackGroup = null
  galaxyNodeGroup = null
  galaxyMasteredGroup = null
  galaxyLinkGroup = null
}

function makeGlowTexture(inner: string, mid: string, outer: string, size = 128) {
  const cacheKey = `glow:${inner}:${mid}:${outer}:${size}`
  const cached = galaxyTextureCache.get(cacheKey)
  if (cached) return cached
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  gradient.addColorStop(0, inner)
  gradient.addColorStop(0.3, mid)
  gradient.addColorStop(1, outer)
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, size, size)
  const texture = new THREE.CanvasTexture(canvas)
  galaxyTextureCache.set(cacheKey, texture)
  return texture
}

function makeNebulaTexture(seedKey: string, width = 1024, height = 1024, density = 28) {
  const cacheKey = `nebula:${seedKey}:${width}:${height}:${density}`
  const cached = galaxyTextureCache.get(cacheKey)
  if (cached) return cached
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')!
  const base = ctx.createLinearGradient(0, 0, width, height)
  base.addColorStop(0, 'rgba(3,6,18,1)')
  base.addColorStop(0.42, 'rgba(7,11,30,1)')
  base.addColorStop(1, 'rgba(2,3,10,1)')
  ctx.fillStyle = base
  ctx.fillRect(0, 0, width, height)

  for (let i = 0; i < density; i += 1) {
    const seed = hashText(`${seedKey}-cloud-${i}`)
    const x = ((seed % 1000) / 1000) * width
    const y = ((hashText(`${seedKey}-cloud-y-${i}`) % 1000) / 1000) * height
    const radius = width * (0.16 + (seed % 340) / 1000)
    const hue = seed % 6
    const colorA = hue === 0
      ? 'rgba(64,116,255,0.3)'
      : hue === 1
        ? 'rgba(182,78,255,0.28)'
        : hue === 2
          ? 'rgba(42,224,240,0.25)'
          : hue === 3
            ? 'rgba(255,156,74,0.21)'
            : hue === 4
              ? 'rgba(58,248,166,0.23)'
              : 'rgba(255,82,182,0.23)'
    const colorB = hue === 0
      ? 'rgba(24,38,84,0.08)'
      : hue === 1
        ? 'rgba(50,32,82,0.08)'
        : hue === 2
          ? 'rgba(16,58,72,0.07)'
          : hue === 3
            ? 'rgba(80,48,34,0.055)'
            : hue === 4
              ? 'rgba(18,68,58,0.06)'
              : 'rgba(70,34,60,0.06)'
    const cloud = ctx.createRadialGradient(x, y, 0, x, y, radius)
    cloud.addColorStop(0, colorA)
    cloud.addColorStop(0.5, colorB)
    cloud.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.fillStyle = cloud
    ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2)
  }

  for (let i = 0; i < 14; i += 1) {
    const seed = hashText(`${seedKey}-dust-lane-${i}`)
    ctx.save()
    ctx.translate(((seed % 1000) / 1000) * width, ((hashText(`${seedKey}-lane-y-${i}`) % 1000) / 1000) * height)
    ctx.rotate(((seed % 360) / 180) * Math.PI)
    const lane = ctx.createLinearGradient(-width * 0.42, 0, width * 0.42, 0)
    lane.addColorStop(0, 'rgba(0,0,0,0)')
    lane.addColorStop(0.46, 'rgba(0,0,0,0.12)')
    lane.addColorStop(0.52, 'rgba(0,0,0,0.22)')
    lane.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.fillStyle = lane
    ctx.fillRect(-width * 0.5, -height * 0.045, width, height * 0.09)
    ctx.restore()
  }

  ctx.globalCompositeOperation = 'screen'
  for (let i = 0; i < 7; i += 1) {
    const seed = hashText(`${seedKey}-soft-veil-${i}`)
    ctx.save()
    ctx.translate(((seed % 1000) / 1000) * width, ((hashText(`${seedKey}-soft-y-${i}`) % 1000) / 1000) * height)
    ctx.rotate(((seed % 160) - 80) * Math.PI / 180)
    const veil = ctx.createLinearGradient(-width * 0.58, 0, width * 0.58, 0)
    veil.addColorStop(0, 'rgba(0,0,0,0)')
    veil.addColorStop(0.36, 'rgba(38,220,240,0.095)')
    veil.addColorStop(0.5, 'rgba(100,126,255,0.125)')
    veil.addColorStop(0.64, 'rgba(238,82,220,0.105)')
    veil.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.fillStyle = veil
    ctx.fillRect(-width * 0.58, -height * 0.085, width * 1.16, height * 0.17)
    ctx.restore()
  }
  ctx.globalCompositeOperation = 'source-over'

  const vignette = ctx.createRadialGradient(width * 0.5, height * 0.5, width * 0.1, width * 0.5, height * 0.5, width * 0.74)
  vignette.addColorStop(0, 'rgba(0,0,0,0)')
  vignette.addColorStop(0.68, 'rgba(0,0,0,0.04)')
  vignette.addColorStop(1, 'rgba(0,0,0,0.5)')
  ctx.fillStyle = vignette
  ctx.fillRect(0, 0, width, height)

  const texture = new THREE.CanvasTexture(canvas)
  if ('SRGBColorSpace' in THREE) texture.colorSpace = THREE.SRGBColorSpace
  texture.needsUpdate = true
  galaxyTextureCache.set(cacheKey, texture)
  return texture
}

function makeDistantGalaxyTexture(seedKey: string, size = 512) {
  const cacheKey = `distant:${seedKey}:${size}`
  const cached = galaxyTextureCache.get(cacheKey)
  if (cached) return cached
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const center = size / 2
  ctx.clearRect(0, 0, size, size)

  const seed = hashText(seedKey)
  ctx.save()
  ctx.translate(center, center)
  ctx.rotate(((seed % 90) - 45) * Math.PI / 180)
  ctx.scale(1, 0.42 + (seed % 18) / 100)

  const palette = seed % 5
  const coreColor = palette === 0 ? 'rgba(255,248,224,0.9)' : palette === 1 ? 'rgba(222,238,255,0.88)' : palette === 2 ? 'rgba(236,214,255,0.86)' : palette === 3 ? 'rgba(208,255,238,0.82)' : 'rgba(255,217,176,0.86)'
  const armA = palette === 0 ? 'rgba(255,220,170,0.4)' : palette === 1 ? 'rgba(145,190,255,0.4)' : palette === 2 ? 'rgba(194,142,255,0.38)' : palette === 3 ? 'rgba(120,236,210,0.34)' : 'rgba(255,154,190,0.32)'
  const armB = palette === 0 ? 'rgba(140,178,255,0.3)' : palette === 1 ? 'rgba(120,230,238,0.28)' : palette === 2 ? 'rgba(255,170,214,0.28)' : palette === 3 ? 'rgba(170,210,255,0.26)' : 'rgba(255,214,130,0.28)'
  const armC = palette === 0 ? 'rgba(190,142,255,0.2)' : palette === 1 ? 'rgba(255,210,158,0.2)' : palette === 2 ? 'rgba(130,220,255,0.2)' : palette === 3 ? 'rgba(255,190,120,0.18)' : 'rgba(150,190,255,0.2)'

  const halo = ctx.createRadialGradient(0, 0, 0, 0, 0, size * 0.48)
  halo.addColorStop(0, coreColor)
  halo.addColorStop(0.08, armA)
  halo.addColorStop(0.28, armB)
  halo.addColorStop(0.62, armC)
  halo.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = halo
  ctx.fillRect(-center, -center, size, size)

  ctx.globalCompositeOperation = 'lighter'
  for (let arm = 0; arm < 3; arm += 1) {
    ctx.beginPath()
    for (let i = 0; i < 190; i += 1) {
      const t = i / 189
      const spin = arm * Math.PI * 0.66 + t * Math.PI * (3.2 + (seed % 12) / 10)
      const radius = 8 + Math.pow(t, 0.74) * size * 0.42
      const wobble = Math.sin(t * Math.PI * 7 + arm) * 5
      const x = Math.cos(spin) * (radius + wobble)
      const y = Math.sin(spin) * (radius * 0.62 + wobble * 0.4)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }
    ctx.strokeStyle = arm === 0 ? armA : arm === 1 ? armB : armC
    ctx.lineWidth = size * (0.028 + arm * 0.007)
    ctx.shadowColor = palette === 2 ? 'rgba(190,130,255,0.5)' : palette === 3 ? 'rgba(110,240,210,0.42)' : 'rgba(140,190,255,0.46)'
    ctx.shadowBlur = 34
    ctx.stroke()
  }

  for (let i = 0; i < 430; i += 1) {
    const dotSeed = hashText(`${seedKey}-dot-${i}`)
    const t = (dotSeed % 1000) / 1000
    const arm = i % 3
    const spin = arm * Math.PI * 0.66 + t * Math.PI * 4.2 + ((dotSeed % 80) / 80)
    const radius = Math.sqrt(t) * size * 0.43
    const x = Math.cos(spin) * radius + ((dotSeed % 30) - 15)
    const y = Math.sin(spin) * radius * 0.55 + ((hashText(`${seedKey}-dot-y-${i}`) % 24) - 12)
    const dot = 0.45 + (dotSeed % 14) / 10
    ctx.fillStyle = i % 7 === 0 ? 'rgba(255,238,190,0.9)' : palette === 2 ? 'rgba(238,212,255,0.82)' : palette === 3 ? 'rgba(194,255,236,0.78)' : palette === 4 ? 'rgba(255,196,220,0.76)' : 'rgba(224,242,255,0.78)'
    ctx.beginPath()
    ctx.arc(x, y, dot, 0, Math.PI * 2)
    ctx.fill()
  }

  const dust = ctx.createLinearGradient(-size * 0.36, 0, size * 0.36, 0)
  dust.addColorStop(0, 'rgba(0,0,0,0)')
  dust.addColorStop(0.48, 'rgba(0,0,0,0.28)')
  dust.addColorStop(0.55, 'rgba(0,0,0,0.18)')
  dust.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.globalCompositeOperation = 'source-over'
  ctx.fillStyle = dust
  ctx.fillRect(-size * 0.38, -size * 0.025, size * 0.76, size * 0.05)
  ctx.restore()

  const fade = ctx.createRadialGradient(center, center, size * 0.08, center, center, size * 0.5)
  fade.addColorStop(0, 'rgba(255,255,255,0)')
  fade.addColorStop(0.78, 'rgba(255,255,255,0)')
  fade.addColorStop(1, 'rgba(0,0,0,0.35)')
  ctx.fillStyle = fade
  ctx.fillRect(0, 0, size, size)

  const texture = new THREE.CanvasTexture(canvas)
  if ('SRGBColorSpace' in THREE) texture.colorSpace = THREE.SRGBColorSpace
  texture.needsUpdate = true
  galaxyTextureCache.set(cacheKey, texture)
  return texture
}

function makeLabelTexture(text: string, subtext = '') {
  const cacheKey = `label:${text}:${subtext}`
  const cached = galaxyTextureCache.get(cacheKey)
  if (cached) return cached
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 96
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.textAlign = 'center'
  ctx.shadowColor = 'rgba(0,0,0,0.9)'
  ctx.shadowBlur = 8
  ctx.fillStyle = 'rgba(245,250,255,0.92)'
  ctx.font = '700 28px Microsoft YaHei, system-ui, sans-serif'
  ctx.fillText(text.slice(0, 9), 128, 40)
  ctx.fillStyle = 'rgba(174,215,255,0.8)'
  ctx.font = '600 18px Microsoft YaHei, system-ui, sans-serif'
  ctx.fillText(subtext, 128, 68)
  const texture = new THREE.CanvasTexture(canvas)
  galaxyTextureCache.set(cacheKey, texture)
  return texture
}

function requestReferenceGalaxyTexture() {
  if (galaxyReferenceTexture) return galaxyReferenceTexture
  if (galaxyReferenceLoading) return null
  galaxyReferenceLoading = true
  const image = new Image()
  image.onload = () => {
    const canvas = document.createElement('canvas')
    canvas.width = 1920
    canvas.height = 1040
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const sourceY = Math.floor(image.height * 0.31)
    const sourceHeight = Math.floor(image.height * 0.37)
    ctx.drawImage(image, 0, sourceY, image.width, sourceHeight, 0, 0, canvas.width, canvas.height)

    const coolTint = ctx.createLinearGradient(0, 0, canvas.width, canvas.height)
    coolTint.addColorStop(0, 'rgba(18, 40, 88, 0.16)')
    coolTint.addColorStop(0.45, 'rgba(255, 232, 188, 0.04)')
    coolTint.addColorStop(1, 'rgba(85, 56, 132, 0.16)')
    ctx.fillStyle = coolTint
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    const coreBloom = ctx.createRadialGradient(canvas.width * 0.5, canvas.height * 0.49, 0, canvas.width * 0.5, canvas.height * 0.49, canvas.width * 0.22)
    coreBloom.addColorStop(0, 'rgba(255,255,246,0.34)')
    coreBloom.addColorStop(0.2, 'rgba(255,230,186,0.16)')
    coreBloom.addColorStop(0.58, 'rgba(120,170,255,0.07)')
    coreBloom.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.fillStyle = coreBloom
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    const edgeFade = ctx.createRadialGradient(canvas.width * 0.5, canvas.height * 0.5, canvas.width * 0.12, canvas.width * 0.5, canvas.height * 0.5, canvas.width * 0.62)
    edgeFade.addColorStop(0, 'rgba(0,0,0,0)')
    edgeFade.addColorStop(0.56, 'rgba(0,0,0,0.12)')
    edgeFade.addColorStop(1, 'rgba(0,0,0,0.9)')
    ctx.fillStyle = edgeFade
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    const texture = new THREE.CanvasTexture(canvas)
    if ('SRGBColorSpace' in THREE) texture.colorSpace = THREE.SRGBColorSpace
    texture.needsUpdate = true
    galaxyReferenceTexture = texture
    galaxyReferenceLoading = false
    galaxyNeedsRebuild = true
    if (activePage.value === 'tagGalaxy') void nextTick(startTagGalaxy)
  }
  image.onerror = () => {
    galaxyReferenceLoading = false
  }
  image.src = '/assets/tag-galaxy-reference.jpg'
  return null
}

function ensureTagGalaxyRenderer() {
  const canvas = galaxyCanvas.value
  if (!canvas || activePage.value !== 'tagGalaxy') return false
  const rect = canvas.getBoundingClientRect()
  const width = Math.max(320, rect.width)
  const height = Math.max(280, rect.height)
  if (!galaxyRenderer) {
    galaxyRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false })
    galaxyRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    galaxyRenderer.setClearColor(0x050817, 1)
  }
  galaxyRenderer.setSize(width, height, false)
  if (!galaxyScene || !galaxyCamera || galaxyNeedsRebuild) rebuildTagGalaxyScene(width, height)
  galaxyCamera.aspect = width / height
  galaxyCamera.position.z = 560 / galaxyZoom.value
  galaxyCamera.updateProjectionMatrix()
  return true
}

function rebuildTagGalaxyScene(width: number, height: number) {
  disposeTagGalaxyScene()
  galaxyScene = new THREE.Scene()
  galaxyCamera = new THREE.PerspectiveCamera(48, width / height, 1, 3000)
  galaxyCamera.position.set(0, 0, 560 / galaxyZoom.value)
  galaxyRaycaster = new THREE.Raycaster()
  galaxyPointer = new THREE.Vector2()

  galaxySkyDome = new THREE.Mesh(
    new THREE.SphereGeometry(1850, 64, 32),
    new THREE.MeshBasicMaterial({
      map: makeNebulaTexture('sky-dome', 1600, 900, 42),
      side: THREE.BackSide,
      transparent: true,
      opacity: 0.96,
      depthWrite: false,
    })
  )
  galaxySkyDome.rotation.set(0.18, -0.22, 0.12)
  galaxyScene.add(galaxySkyDome)

  const atmosphereConfigs = [
    { key: 'near-left', x: -760, y: 120, z: -430, w: 1500, h: 1040, opacity: 0.3, rotate: -0.42 },
    { key: 'near-right', x: 820, y: -80, z: -520, w: 1650, h: 1120, opacity: 0.27, rotate: 0.36 },
    { key: 'upper-veil', x: 80, y: 520, z: -670, w: 2150, h: 880, opacity: 0.26, rotate: 0.08 },
    { key: 'lower-veil', x: -70, y: -560, z: -720, w: 2150, h: 880, opacity: 0.24, rotate: -0.1 },
    { key: 'far-wrap', x: 0, y: 0, z: -980, w: 3000, h: 1900, opacity: 0.34, rotate: 0.02 },
    { key: 'diagonal-mist-a', x: -220, y: 180, z: -820, w: 2500, h: 620, opacity: 0.2, rotate: -0.36 },
    { key: 'diagonal-mist-b', x: 260, y: -160, z: -900, w: 2500, h: 620, opacity: 0.18, rotate: 0.32 },
  ]
  for (const config of atmosphereConfigs) {
    const layer = new THREE.Sprite(new THREE.SpriteMaterial({
      map: makeNebulaTexture(`atmosphere-${config.key}`, 1024, 1024, 30),
      transparent: true,
      opacity: config.opacity,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }))
    layer.position.set(config.x, config.y, config.z)
    layer.scale.set(config.w, config.h, 1)
    layer.rotation.z = config.rotate
    layer.userData = { ...config, baseX: config.x, baseY: config.y, baseZ: config.z, baseScaleX: config.w, baseScaleY: config.h, type: 'atmosphere' }
    galaxyAtmosphereLayers.push(layer)
    galaxyScene.add(layer)
  }

  const backgroundGalaxyConfigs = [
    { key: 'spiral-left', x: -980, y: 350, z: -1180, w: 470, h: 290, opacity: 0.42, rotate: -0.28, speed: 0.018 },
    { key: 'spiral-right', x: 1080, y: 260, z: -1260, w: 550, h: 330, opacity: 0.4, rotate: 0.32, speed: -0.014 },
    { key: 'tiny-upper', x: 520, y: 620, z: -1420, w: 320, h: 200, opacity: 0.34, rotate: -0.7, speed: 0.022 },
    { key: 'edge-lower', x: -720, y: -610, z: -1320, w: 660, h: 370, opacity: 0.36, rotate: 0.18, speed: -0.012 },
    { key: 'far-center', x: 40, y: -470, z: -1540, w: 370, h: 230, opacity: 0.3, rotate: -0.08, speed: 0.016 },
    { key: 'ghost-far-left', x: -1380, y: -280, z: -1580, w: 410, h: 250, opacity: 0.28, rotate: 0.48, speed: 0.01 },
    { key: 'ghost-far-right', x: 1380, y: -420, z: -1620, w: 350, h: 220, opacity: 0.26, rotate: -0.44, speed: -0.012 },
    { key: 'rim-upper-left-a', x: -1580, y: 760, z: -1660, w: 290, h: 180, opacity: 0.34, rotate: -0.18, speed: 0.013 },
    { key: 'rim-upper-left-b', x: -1280, y: 900, z: -1780, w: 230, h: 142, opacity: 0.28, rotate: 0.62, speed: -0.017 },
    { key: 'rim-upper-right-a', x: 1540, y: 760, z: -1700, w: 310, h: 190, opacity: 0.33, rotate: -0.56, speed: 0.014 },
    { key: 'rim-upper-right-b', x: 1260, y: 930, z: -1840, w: 225, h: 140, opacity: 0.27, rotate: 0.28, speed: 0.018 },
    { key: 'rim-lower-left-a', x: -1600, y: -820, z: -1720, w: 330, h: 200, opacity: 0.32, rotate: 0.34, speed: -0.015 },
    { key: 'rim-lower-right-a', x: 1580, y: -850, z: -1740, w: 300, h: 190, opacity: 0.31, rotate: -0.32, speed: 0.016 },
    { key: 'distant-cluster-top', x: 40, y: 1010, z: -1900, w: 250, h: 155, opacity: 0.25, rotate: -0.12, speed: 0.02 },
    { key: 'distant-cluster-bottom', x: -120, y: -1040, z: -1880, w: 270, h: 165, opacity: 0.26, rotate: 0.42, speed: -0.018 },
  ]
  for (const config of backgroundGalaxyConfigs) {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
      map: makeDistantGalaxyTexture(`background-galaxy-${config.key}`, 640),
      transparent: true,
      opacity: config.opacity,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      rotation: config.rotate,
    }))
    sprite.position.set(config.x, config.y, config.z)
    sprite.scale.set(config.w, config.h, 1)
    sprite.userData = { ...config, baseX: config.x, baseY: config.y, baseZ: config.z, baseScaleX: config.w, baseScaleY: config.h, type: 'background-galaxy' }
    galaxyBackgroundSystems.push(sprite)
    galaxyScene.add(sprite)
  }

  const backgroundNebulaConfigs = [
    { key: 'blue-cloud-left', x: -1180, y: -120, z: -1100, w: 1220, h: 980, opacity: 0.22, rotate: -0.22, speed: 0.006 },
    { key: 'violet-cloud-right', x: 1160, y: -260, z: -1160, w: 1320, h: 1020, opacity: 0.2, rotate: 0.26, speed: -0.007 },
    { key: 'top-aurora', x: 0, y: 820, z: -1250, w: 2200, h: 640, opacity: 0.18, rotate: 0.04, speed: 0.004 },
    { key: 'bottom-aurora', x: -180, y: -820, z: -1220, w: 2200, h: 680, opacity: 0.17, rotate: -0.08, speed: -0.005 },
    { key: 'center-haze', x: 0, y: 80, z: -1360, w: 2400, h: 1200, opacity: 0.16, rotate: 0.16, speed: 0.003 },
    { key: 'left-shadow-haze', x: -900, y: 520, z: -1500, w: 1500, h: 950, opacity: 0.14, rotate: -0.48, speed: -0.004 },
    { key: 'teal-fog-field', x: 760, y: 540, z: -1460, w: 1450, h: 940, opacity: 0.15, rotate: 0.58, speed: 0.005 },
    { key: 'rose-violet-field', x: -1020, y: -500, z: -1480, w: 1520, h: 980, opacity: 0.14, rotate: -0.62, speed: -0.004 },
    { key: 'amber-dust-field', x: 160, y: -80, z: -1680, w: 2600, h: 900, opacity: 0.12, rotate: 0.24, speed: 0.003 },
    { key: 'bright-cyan-nebula', x: -1460, y: 220, z: -1320, w: 1120, h: 820, opacity: 0.4, rotate: 0.18, speed: 0.006 },
    { key: 'bright-rose-nebula', x: 1450, y: 420, z: -1380, w: 1180, h: 860, opacity: 0.38, rotate: -0.26, speed: -0.006 },
    { key: 'bright-amber-nebula', x: 980, y: -760, z: -1500, w: 1220, h: 780, opacity: 0.34, rotate: 0.4, speed: 0.005 },
    { key: 'bright-violet-nebula', x: -1120, y: -860, z: -1540, w: 1260, h: 820, opacity: 0.34, rotate: -0.36, speed: -0.005 },
  ]
  for (const config of backgroundNebulaConfigs) {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
      map: makeNebulaTexture(`background-nebula-${config.key}`, 1024, 1024, 36),
      transparent: true,
      opacity: config.opacity,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      rotation: config.rotate,
    }))
    sprite.position.set(config.x, config.y, config.z)
    sprite.scale.set(config.w, config.h, 1)
    sprite.userData = { ...config, baseX: config.x, baseY: config.y, baseZ: config.z, baseScaleX: config.w, baseScaleY: config.h, type: 'background-nebula' }
    galaxyBackgroundSystems.push(sprite)
    galaxyScene.add(sprite)
  }

  const deepPositions: number[] = []
  const deepColors: number[] = []
  for (let i = 0; i < 6200; i += 1) {
    const seed = hashText(`deep-space-${i}`)
    const ySeed = hashText(`deep-space-y-${i}`)
    const zSeed = hashText(`deep-space-z-${i}`)
    deepPositions.push(((seed % 1000) / 1000 - 0.5) * 3000)
    deepPositions.push(((ySeed % 1000) / 1000 - 0.5) * 1800)
    deepPositions.push(-900 + ((zSeed % 1000) / 1000 - 0.5) * 700)
    const warmth = (hashText(`deep-space-c-${i}`) % 100) / 100
    deepColors.push(0.56 + warmth * 0.34, 0.66 + warmth * 0.28, 0.86 + warmth * 0.14)
  }
  const deepGeometry = new THREE.BufferGeometry()
  deepGeometry.setAttribute('position', new THREE.Float32BufferAttribute(deepPositions, 3))
  deepGeometry.setAttribute('color', new THREE.Float32BufferAttribute(deepColors, 3))
  galaxyDeepField = new THREE.Points(deepGeometry, new THREE.PointsMaterial({ size: 2.25, vertexColors: true, transparent: true, opacity: 0.58, blending: THREE.AdditiveBlending, depthWrite: false }))
  galaxyScene.add(galaxyDeepField)

  const spaceWashTexture = makeGlowTexture('rgba(104,128,255,0.46)', 'rgba(62,72,170,0.3)', 'rgba(0,0,0,0)', 256)
  const spaceWash = new THREE.Sprite(new THREE.SpriteMaterial({ map: spaceWashTexture, transparent: true, opacity: 0.62, blending: THREE.AdditiveBlending, depthWrite: false }))
  spaceWash.position.set(0, 0, -1080)
  spaceWash.scale.set(3000, 1900, 1)
  spaceWash.userData = { baseX: 0, baseY: 0, baseScaleX: 3000, baseScaleY: 1900, type: 'wide-nebula' }
  galaxyNebulae.push(spaceWash)
  galaxyScene.add(spaceWash)

  galaxyBackdrop = new THREE.Group()
  const referenceTexture = requestReferenceGalaxyTexture()
  if (referenceTexture) {
    const aspect = width / Math.max(height, 1)
    const backdropWidth = aspect > 1.25 ? 1900 : 1500
    const backdropHeight = aspect > 1.25 ? 1060 : 1160
    const photoPlane = new THREE.Mesh(
      new THREE.PlaneGeometry(backdropWidth, backdropHeight, 1, 1),
      new THREE.MeshBasicMaterial({ map: referenceTexture, transparent: true, opacity: 0.68, blending: THREE.AdditiveBlending, depthWrite: false })
    )
    photoPlane.position.set(0, 0, -280)
    photoPlane.rotation.z = -0.015
    photoPlane.userData = { baseScaleX: 1, baseScaleY: 1, type: 'photo' }
    galaxyBackdrop.add(photoPlane)
  }
  const wideNebulaTexture = makeGlowTexture('rgba(94,170,255,0.24)', 'rgba(154,70,230,0.16)', 'rgba(0,0,0,0)', 256)
  for (let i = 0; i < 5; i += 1) {
    const wide = new THREE.Sprite(new THREE.SpriteMaterial({ map: wideNebulaTexture, transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending, depthWrite: false }))
    const seed = hashText(`wide-nebula-${i}`)
    wide.position.set(((seed % 1000) / 1000 - 0.5) * 1500, ((hashText(`wide-nebula-y-${i}`) % 1000) / 1000 - 0.5) * 820, -760 + i * 36)
    const wideW = 680 + (seed % 420)
    const wideH = 360 + (seed % 260)
    wide.scale.set(wideW, wideH, 1)
    wide.userData = { baseX: wide.position.x, baseY: wide.position.y, baseScaleX: wideW, baseScaleY: wideH, type: 'wide-nebula' }
    galaxyNebulae.push(wide)
    galaxyScene.add(wide)
  }

  const softHaloTexture = makeGlowTexture('rgba(255,246,220,0.42)', 'rgba(98,145,230,0.17)', 'rgba(0,0,0,0)', 256)
  const innerHalo = new THREE.Sprite(new THREE.SpriteMaterial({ map: softHaloTexture, transparent: true, opacity: referenceTexture ? 0.34 : 0.64, blending: THREE.AdditiveBlending, depthWrite: false }))
  innerHalo.position.set(0, -6, -205)
  innerHalo.scale.set(680, 460, 1)
  innerHalo.userData = { baseScaleX: 680, baseScaleY: 460 }
  galaxyBackdrop.add(innerHalo)
  const edgeMistTexture = makeGlowTexture('rgba(110,155,240,0.13)', 'rgba(70,84,170,0.09)', 'rgba(0,0,0,0)', 256)
  for (let i = 0; i < 4; i += 1) {
    const mist = new THREE.Sprite(new THREE.SpriteMaterial({ map: edgeMistTexture, transparent: true, opacity: 0.13, blending: THREE.AdditiveBlending, depthWrite: false }))
    const seed = hashText(`reference-mist-${i}`)
    mist.position.set(((seed % 1000) / 1000 - 0.5) * 1100, ((hashText(`reference-mist-y-${i}`) % 1000) / 1000 - 0.5) * 520, -245 + i * 8)
    const mistWidth = 520 + (seed % 320)
    const mistHeight = 240 + (seed % 210)
    mist.scale.set(mistWidth, mistHeight, 1)
    mist.userData = { baseScaleX: mistWidth, baseScaleY: mistHeight }
    galaxyBackdrop.add(mist)
  }
  galaxyScene.add(galaxyBackdrop)

  const starPositions: number[] = []
  const starColors: number[] = []
  for (let i = 0; i < 4600; i += 1) {
    const seed = hashText(`three-star-${i}`)
    starPositions.push(((seed % 1000) / 1000 - 0.5) * 2300)
    starPositions.push(((hashText(`three-star-y-${i}`) % 1000) / 1000 - 0.5) * 1350)
    starPositions.push(((hashText(`three-star-z-${i}`) % 1000) / 1000 - 0.5) * 1300)
    const cool = (seed % 100) / 100
    starColors.push(0.72 + cool * 0.28, 0.82 + cool * 0.16, 1)
  }
  const starGeometry = new THREE.BufferGeometry()
  starGeometry.setAttribute('position', new THREE.Float32BufferAttribute(starPositions, 3))
  starGeometry.setAttribute('color', new THREE.Float32BufferAttribute(starColors, 3))
  galaxyStarField = new THREE.Points(starGeometry, new THREE.PointsMaterial({ size: 2.05, vertexColors: true, transparent: true, opacity: referenceTexture ? 0.58 : 0.82, blending: THREE.AdditiveBlending, depthWrite: false }))
  galaxyScene.add(galaxyStarField)

  const dustPositions: number[] = []
  const dustColors: number[] = []
  for (let i = 0; i < 4200; i += 1) {
    const t = i / 4200
    const seed = hashText(`three-dust-${i}`)
    const arm = i % 2
    const spin = arm * Math.PI + t * Math.PI * 9.8 + (seed % 80) / 90
    const radius = 28 + Math.sqrt(t) * 780
    dustPositions.push(Math.cos(spin) * radius + ((seed % 100) - 50) * 0.8)
    dustPositions.push(Math.sin(spin * 1.3) * 16 + ((seed % 40) - 20) * 0.22)
    dustPositions.push(Math.sin(spin) * radius * 0.23 + ((hashText(`three-dust-z-${i}`) % 60) - 30))
    dustColors.push(i % 7 === 0 ? 1 : 0.58, i % 7 === 0 ? 0.9 : 0.72, i % 5 === 0 ? 0.84 : 1)
  }
  const dustGeometry = new THREE.BufferGeometry()
  dustGeometry.setAttribute('position', new THREE.Float32BufferAttribute(dustPositions, 3))
  dustGeometry.setAttribute('color', new THREE.Float32BufferAttribute(dustColors, 3))
  galaxyDustField = new THREE.Points(dustGeometry, new THREE.PointsMaterial({ size: 2.65, vertexColors: true, transparent: true, opacity: referenceTexture ? 0.28 : 0.42, blending: THREE.AdditiveBlending, depthWrite: false }))
  galaxyDustField.rotation.z = -0.25
  galaxyScene.add(galaxyDustField)

  galaxyTrackGroup = new THREE.Group()
  const trackColors = [0x91b9ff, 0xffd8a6, 0xc59cff, 0x72dcc8]
  for (let arm = 0; arm < 8; arm += 1) {
    const points: any[] = []
    const armOffset = arm * Math.PI * 0.5
    const inner = arm % 2 === 0 ? 36 : 58
    const outer = arm % 2 === 0 ? 760 : 680
    for (let i = 0; i < 210; i += 1) {
      const t = i / 209
      const spin = armOffset + t * Math.PI * (2.65 + (arm % 3) * 0.38)
      const radius = inner + Math.pow(t, 0.78) * outer
      const wave = Math.sin(t * Math.PI * 5 + arm) * (8 + arm * 0.8)
      points.push(new THREE.Vector3(
        Math.cos(spin) * (radius + wave),
        Math.sin(spin * 1.2) * (11 + arm * 0.8),
        Math.sin(spin) * (radius * 0.24 + wave * 0.35)
      ))
    }
    const geometry = new THREE.BufferGeometry().setFromPoints(points)
    const material = new THREE.LineBasicMaterial({
      color: trackColors[arm % trackColors.length],
      transparent: true,
      opacity: arm % 2 === 0 ? 0.36 : 0.22,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
    const line = new THREE.Line(geometry, material)
    galaxyTrackGroup.add(line)
  }
  galaxyTrackGroup.rotation.z = -0.25
  galaxyScene.add(galaxyTrackGroup)

  const nebulaTexture = makeGlowTexture('rgba(140,190,255,0.12)', 'rgba(108,92,210,0.08)', 'rgba(0,0,0,0)', 256)
  for (let i = 0; i < 5; i += 1) {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: nebulaTexture, transparent: true, opacity: referenceTexture ? 0.11 : 0.25, blending: THREE.AdditiveBlending, depthWrite: false }))
    const seed = hashText(`three-nebula-${i}`)
    sprite.position.set(((seed % 1000) / 1000 - 0.5) * 820, ((hashText(`n-y-${i}`) % 1000) / 1000 - 0.5) * 330, -150 + i * 48)
    const nebulaW = 320 + (seed % 220)
    const nebulaH = 145 + (seed % 120)
    sprite.scale.set(nebulaW, nebulaH, 1)
    sprite.userData = { baseX: sprite.position.x, baseY: sprite.position.y, baseScaleX: nebulaW, baseScaleY: nebulaH, type: 'inner-nebula' }
    galaxyNebulae.push(sprite)
    galaxyScene.add(sprite)
  }

  galaxyCore = new THREE.Group()
  const coreTexture = makeGlowTexture('rgba(255,255,255,0.96)', 'rgba(255,224,180,0.34)', 'rgba(110,160,255,0)', 256)
  const coreBloomTexture = makeGlowTexture('rgba(255,244,210,0.42)', 'rgba(120,168,255,0.14)', 'rgba(0,0,0,0)', 256)
  const coreMistTexture = makeGlowTexture('rgba(210,232,255,0.2)', 'rgba(145,104,210,0.1)', 'rgba(0,0,0,0)', 256)
  const coreGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: coreTexture, transparent: true, opacity: referenceTexture ? 0.62 : 0.8, blending: THREE.AdditiveBlending, depthWrite: false }))
  coreGlow.scale.set(260, 220, 1)
  const coreBloom = new THREE.Sprite(new THREE.SpriteMaterial({ map: coreBloomTexture, transparent: true, opacity: referenceTexture ? 0.5 : 0.66, blending: THREE.AdditiveBlending, depthWrite: false }))
  coreBloom.scale.set(470, 360, 1)
  const coreMist = new THREE.Sprite(new THREE.SpriteMaterial({ map: coreMistTexture, transparent: true, opacity: 0.34, blending: THREE.AdditiveBlending, depthWrite: false }))
  coreMist.scale.set(640, 430, 1)
  galaxyCore.add(coreMist, coreBloom, coreGlow)
  galaxyScene.add(galaxyCore)

  galaxyLinkGroup = new THREE.Group()
  galaxyNodeGroup = new THREE.Group()
  galaxyScene.add(galaxyLinkGroup, galaxyNodeGroup)
  const nodeMap = new Map<string, any>()
  for (const node of tagGalaxy.value.nodes) {
    const active = activeGalaxyTag.value === node.tag
    const related = activeGalaxyTag.value && node.isRelated
    const texture = makeGlowTexture(
      active ? 'rgba(104,255,198,1)' : related ? 'rgba(106,210,255,0.98)' : `hsla(${node.hue},100%,68%,0.96)`,
      active ? 'rgba(118,255,210,0.68)' : related ? 'rgba(94,190,255,0.58)' : `hsla(${node.hue},100%,58%,0.5)`,
      active ? 'rgba(34,255,185,0)' : related ? 'rgba(64,180,255,0)' : `hsla(${node.hue},100%,54%,0)`,
      128
    )
    const star = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: active ? 1 : related ? 0.78 : 0.5 }))
    star.scale.set(active ? 48 : related ? 36 : 24, active ? 48 : related ? 36 : 24, 1)
    star.userData = { tag: node.tag, node }
    const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: makeLabelTexture(node.tag, `${node.count}题`), transparent: true, depthWrite: false, opacity: active ? 0.82 : related ? 0.56 : 0.16 }))
    label.position.y = active ? -36 : -30
    label.scale.set(active ? 84 : 68, active ? 30 : 24, 1)
    const group = new THREE.Group()
    group.add(star, label)
    group.userData = { tag: node.tag, node, star, label }
    galaxyNodeGroup.add(group)
    galaxyNodeMeshes.push(group)
    nodeMap.set(node.tag, group)
  }

  galaxyMasteredGroup = new THREE.Group()
  masteredGalaxyStars.value.forEach((item: any, index: number) => {
    const seed = hashText(`${item.id || item.tag}-${index}`)
    const hue = Number(item.hue ?? (38 + seed % 270))
    const masteredTexture = makeGlowTexture(`hsla(${hue},100%,72%,1)`, `hsla(${hue + 22},100%,58%,0.76)`, `hsla(${hue + 46},100%,48%,0)`, 128)
    const angle = (seed % 628) / 100
    const radius = 120 + (seed % 520)
    const y = ((hashText(`mastered-y-${item.id || index}`) % 1000) / 1000 - 0.5) * 250
    const star = new THREE.Sprite(new THREE.SpriteMaterial({
      map: masteredTexture,
      transparent: true,
      opacity: 0.96,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }))
    const size = 18 + (seed % 16)
    star.position.set(Math.cos(angle) * radius, y, Math.sin(angle) * radius * 0.34)
    star.scale.set(size, size, 1)
    star.userData = { baseSize: size, phase: angle, type: 'mastered-star' }
    galaxyMasteredGroup.add(star)
  })
  galaxyMasteredGroup.rotation.z = -0.25
  galaxyScene.add(galaxyMasteredGroup)

  for (const link of tagGalaxy.value.links) {
    const a = nodeMap.get(link.source)
    const b = nodeMap.get(link.target)
    if (!a || !b) continue
    const selectedLink = activeGalaxyTag.value && (link.source === activeGalaxyTag.value || link.target === activeGalaxyTag.value)
    const geometry = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()])
    const material = new THREE.LineBasicMaterial({ color: selectedLink ? 0xd8f2ff : 0x6ca8ff, transparent: true, opacity: selectedLink ? 0.56 : activeGalaxyTag.value ? 0.12 : 0.28, blending: THREE.AdditiveBlending })
    const line = new THREE.Line(geometry, material)
    line.userData = { source: a, target: b, link }
    galaxyLinkGroup.add(line)
    galaxyLinkMeshes.push(line)
  }
  galaxyNeedsRebuild = false
}

function updateThreeNodePosition(group: any, time: number) {
  const node = group.userData.node
  let x = node.x
  let y = node.y
  let z = node.z
  if (node.focusMode) {
    if (node.isCenter) {
      x = Math.sin(time * 1.5) * 5
      y = Math.cos(time * 1.1) * 4
      z = Math.cos(time * 1.3) * 5
    } else {
      const phase = node.orbitPhase + time * (node.orbitSpeed || 0.25)
      x = Math.cos(phase) * node.orbitRadius
      z = Math.sin(phase) * node.orbitRadius
      y = node.y * 0.58 + Math.sin(phase * 1.7 + time) * (node.isRelated ? 18 : 34)
    }
  }
  group.position.set(x, y, z)
}

function refreshGalaxyFocusState() {
  if (!galaxyNodeGroup || !galaxyLinkGroup) return false
  const nodeLookup = new Map(tagGalaxy.value.nodes.map((node: any) => [node.tag, node]))
  galaxyNodeGroup.children.forEach((group: any) => {
    const node = nodeLookup.get(group.userData.tag) || group.userData.node
    const active = activeGalaxyTag.value === group.userData.tag
    const related = Boolean(activeGalaxyTag.value && node?.isRelated)
    group.userData.node = node
    group.visible = true
    const star = group.userData.star
    const label = group.userData.label
    if (star) {
      star.visible = true
      star.material.opacity = active ? 1 : related ? 0.78 : activeGalaxyTag.value ? 0.42 : 0.5
      star.scale.set(active ? 52 : related ? 40 : 28, active ? 52 : related ? 40 : 28, 1)
    }
    if (label) {
      label.visible = true
      label.material.opacity = active ? 0.88 : related ? 0.62 : activeGalaxyTag.value ? 0.22 : 0.32
      label.position.y = active ? -38 : -31
      label.scale.set(active ? 88 : related ? 74 : 64, active ? 32 : related ? 26 : 22, 1)
    }
  })
  for (const line of galaxyLinkMeshes) {
    const link = line.userData.link
    const selectedLink = activeGalaxyTag.value && (link.source === activeGalaxyTag.value || link.target === activeGalaxyTag.value)
    line.visible = true
    line.material.color.set(selectedLink ? 0xd8f2ff : 0x7fb4ff)
    line.material.opacity = selectedLink ? 0.62 : activeGalaxyTag.value ? 0.18 : 0.32
  }
  return true
}

function animateTagGalaxy() {
  if (!ensureTagGalaxyRenderer() || !galaxyRenderer || !galaxyScene || !galaxyCamera || activePage.value !== 'tagGalaxy') return
  const time = galaxyAngle.value
  galaxyAngle.value += 0.006
  galaxyMouse.x += (galaxyMouse.targetX - galaxyMouse.x) * 0.08
  galaxyMouse.y += (galaxyMouse.targetY - galaxyMouse.y) * 0.08
  const mouseDistance = Math.min(1, Math.hypot(galaxyMouse.x, galaxyMouse.y))
  const interactiveScale = 1 + mouseDistance * 0.14
  galaxyScene.rotation.y = Math.sin(time * 0.22) * 0.04 + galaxyMouse.x * 0.08
  galaxyScene.rotation.x = galaxyMouse.y * 0.035
  galaxyCamera.position.x = -galaxyMouse.x * 26
  galaxyCamera.position.y = galaxyMouse.y * 18
  galaxyCamera.position.z = 560 / Math.max(0.5, galaxyZoom.value * (1 + mouseDistance * 0.08))
  galaxyCamera.lookAt(galaxyMouse.x * 16, -galaxyMouse.y * 10, 0)
  if (galaxySkyDome) {
    galaxySkyDome.rotation.y = -0.22 + time * 0.012 + galaxyMouse.x * 0.018
    galaxySkyDome.rotation.x = 0.18 + Math.sin(time * 0.16) * 0.025 + galaxyMouse.y * 0.012
    galaxySkyDome.rotation.z = 0.12 + time * 0.006
  }
  galaxyAtmosphereLayers.forEach((layer, index) => {
    const depth = 1 + index * 0.22
    const driftX = Math.sin(time * (0.16 + index * 0.025) + index) * (22 + index * 8)
    const driftY = Math.cos(time * (0.13 + index * 0.02) + index) * (14 + index * 6)
    const pulse = 1 + Math.sin(time * (0.22 + index * 0.035) + index) * 0.035
    layer.position.x = layer.userData.baseX + driftX - galaxyMouse.x * 42 / depth
    layer.position.y = layer.userData.baseY + driftY + galaxyMouse.y * 30 / depth
    layer.position.z = layer.userData.baseZ + Math.sin(time * 0.12 + index) * 18
    layer.scale.set(layer.userData.baseScaleX * pulse, layer.userData.baseScaleY * pulse, 1)
    layer.rotation.z = layer.userData.rotate + time * (0.006 + index * 0.002) * (index % 2 ? -1 : 1)
    if (layer.material) layer.material.opacity = layer.userData.opacity + Math.sin(time * 0.28 + index) * 0.022
  })
  galaxyBackgroundSystems.forEach((system, index) => {
    const isGalaxy = system.userData.type === 'background-galaxy'
    const isBrightNebula = !isGalaxy && String(system.userData.key || '').includes('bright')
    const depth = Math.max(1, Math.abs(system.userData.baseZ || -1000) / 760)
    const driftX = Math.sin(time * (0.11 + index * 0.014) + index) * (isGalaxy ? 10 : isBrightNebula ? 36 : 28)
    const driftY = Math.cos(time * (0.09 + index * 0.012) + index) * (isGalaxy ? 7 : isBrightNebula ? 28 : 20)
    const pulse = 1 + Math.sin(time * (isGalaxy ? 0.18 : 0.24) + index) * (isGalaxy ? 0.018 : isBrightNebula ? 0.055 : 0.04)
    system.position.x = system.userData.baseX + driftX - galaxyMouse.x * (isGalaxy ? 20 : 34) / depth
    system.position.y = system.userData.baseY + driftY + galaxyMouse.y * (isGalaxy ? 14 : 26) / depth
    system.position.z = system.userData.baseZ + Math.sin(time * 0.08 + index) * (isGalaxy ? 10 : 22)
    system.scale.set(system.userData.baseScaleX * pulse, system.userData.baseScaleY * pulse, 1)
    if (system.material) {
      system.material.rotation = system.userData.rotate + time * system.userData.speed
      system.material.opacity = system.userData.opacity + Math.sin(time * 0.22 + index) * (isGalaxy ? 0.04 : isBrightNebula ? 0.06 : 0.036)
    }
  })
  if (galaxyDeepField) {
    galaxyDeepField.rotation.z = time * 0.01
    galaxyDeepField.rotation.y += 0.00045 + mouseDistance * 0.00025
    galaxyDeepField.rotation.x = Math.sin(time * 0.18) * 0.035 + galaxyMouse.y * 0.02
  }
  if (galaxyBackdrop) {
    galaxyBackdrop.rotation.z = -0.018 + time * 0.055 + galaxyMouse.x * 0.035
    galaxyBackdrop.rotation.x = galaxyMouse.y * 0.028
    galaxyBackdrop.rotation.y = -galaxyMouse.x * 0.036
    galaxyBackdrop.scale.setScalar(interactiveScale + Math.sin(time * 0.42) * 0.012)
    galaxyBackdrop.children.forEach((child: any, index: number) => {
      const photoLayer = child.userData.type === 'photo'
      const pulse = photoLayer ? 1 + Math.sin(time * 0.5) * 0.012 : 1 + Math.sin(time * 0.72 + index) * 0.025
      child.scale.set((child.userData.baseScaleX || child.scale.x) * pulse, (child.userData.baseScaleY || child.scale.y) * pulse, 1)
      if (child.material) {
        child.material.opacity = photoLayer
          ? 0.68 + Math.sin(time * 0.7) * 0.018
          : index === 1 ? 0.3 + Math.sin(time * 0.8) * 0.035 : 0.1 + Math.sin(time * 0.55 + index) * 0.024
      }
    })
  }
  if (galaxyStarField) {
    galaxyStarField.rotation.z = -time * 0.008
    galaxyStarField.rotation.y += 0.0011 + mouseDistance * 0.0004
    galaxyStarField.rotation.x = galaxyMouse.y * 0.025
  }
  if (galaxyDustField) {
    galaxyDustField.rotation.y += 0.0032 + mouseDistance * 0.001
    galaxyDustField.rotation.x = galaxyMouse.y * 0.035
    galaxyDustField.rotation.z = -0.25 + time * 0.085 + Math.sin(time * 0.4) * 0.018 + galaxyMouse.x * 0.05
  }
  if (galaxyTrackGroup) {
    galaxyTrackGroup.rotation.y = galaxyDustField?.rotation.y || 0
    galaxyTrackGroup.rotation.x = galaxyMouse.y * 0.034
    galaxyTrackGroup.rotation.z = -0.25 + time * 0.09 + Math.sin(time * 0.4) * 0.016 + galaxyMouse.x * 0.05
    galaxyTrackGroup.children.forEach((line: any, index: number) => {
      if (line.material) line.material.opacity = (index % 2 === 0 ? 0.34 : 0.2) + Math.sin(time * 0.7 + index) * 0.055
    })
  }
  if (galaxyMasteredGroup) {
    galaxyMasteredGroup.rotation.y = galaxyDustField?.rotation.y || 0
    galaxyMasteredGroup.rotation.x = galaxyMouse.y * 0.032
    galaxyMasteredGroup.rotation.z = -0.25 + time * 0.07 + galaxyMouse.x * 0.04
    galaxyMasteredGroup.children.forEach((star: any, index: number) => {
      const pulse = 1 + Math.sin(time * 1.8 + star.userData.phase + index) * 0.22
      const baseSize = star.userData.baseSize || 20
      star.scale.set(baseSize * pulse, baseSize * pulse, 1)
      if (star.material) star.material.opacity = 0.74 + Math.sin(time * 1.4 + index) * 0.22
    })
  }
  if (galaxyCore) {
    const pulse = 1 + mouseDistance * 0.08 + Math.sin(time * 2.4) * 0.045
    galaxyCore.scale.setScalar(pulse)
    galaxyCore.rotation.y += 0.01
    galaxyCore.rotation.z = time * 0.09
  }
  galaxyNebulae.forEach((sprite, index) => {
    const wide = sprite.userData.type === 'wide-nebula'
    const pulse = 1 + Math.sin(time * (wide ? 0.34 : 0.8) + index) * (wide ? 0.035 : 0.045)
    sprite.material.opacity = wide ? 0.1 + Math.sin(time * 0.38 + index) * 0.024 : 0.09 + Math.sin(time * 0.8 + index) * 0.026
    sprite.position.x = (sprite.userData.baseX || sprite.position.x) + Math.sin(time * 0.22 + index) * (wide ? 26 : 8)
    sprite.position.y = (sprite.userData.baseY || sprite.position.y) + Math.cos(time * 0.18 + index) * (wide ? 18 : 6)
    sprite.scale.set((sprite.userData.baseScaleX || sprite.scale.x) * pulse, (sprite.userData.baseScaleY || sprite.scale.y) * pulse, 1)
    sprite.rotation.z += (wide ? 0.00025 : 0.0009) * (index % 2 ? -1 : 1)
  })
  const projected: { tag: string; x: number; y: number; radius: number }[] = []
  galaxyNodeGroup?.children.forEach((group: any) => {
    updateThreeNodePosition(group, time)
    group.lookAt(galaxyCamera.position)
    const screen = group.position.clone().project(galaxyCamera)
    const rect = galaxyCanvas.value?.getBoundingClientRect()
    if (rect) projected.push({ tag: group.userData.tag, x: (screen.x * 0.5 + 0.5) * rect.width, y: (-screen.y * 0.5 + 0.5) * rect.height, radius: 24 })
  })
  galaxyTargets.value = projected
  for (const line of galaxyLinkMeshes) {
    line.geometry.setFromPoints([line.userData.source.position, line.userData.target.position])
    line.geometry.attributes.position.needsUpdate = true
  }
  galaxyRenderer.render(galaxyScene, galaxyCamera)
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
    galaxyFrame = null
    return
  }
  galaxyFrame = window.requestAnimationFrame(animateTagGalaxy)
}

function drawTagGalaxy() {
  const canvas = galaxyCanvas.value
  if (!canvas || activePage.value !== 'tagGalaxy') return
  const rect = canvas.getBoundingClientRect()
  const dpr = window.devicePixelRatio || 1
  const width = Math.max(320, rect.width)
  const height = Math.max(280, rect.height)
  if (canvas.width !== Math.floor(width * dpr) || canvas.height !== Math.floor(height * dpr)) {
    canvas.width = Math.floor(width * dpr)
    canvas.height = Math.floor(height * dpr)
  }
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)

  ctx.fillStyle = '#02030a'
  ctx.fillRect(0, 0, width, height)

  const nodes = tagGalaxy.value.nodes
  const links = tagGalaxy.value.links
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const angle = galaxyAngle.value
  if (!reducedMotion) galaxyAngle.value += 0.006
  const time = angle * 160
  const projected = new Map<string, any>()
  const centerX = width / 2
  const centerY = height / 2
  const camera = 430
  const zoom = galaxyZoom.value
  const scaleBase = Math.min(width, height) / 390 * zoom

  const skyGlow = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, Math.max(width, height) * 0.65)
  skyGlow.addColorStop(0, 'rgba(56, 85, 130, 0.22)')
  skyGlow.addColorStop(0.45, 'rgba(18, 30, 62, 0.2)')
  skyGlow.addColorStop(1, 'rgba(0, 0, 0, 0)')
  ctx.fillStyle = skyGlow
  ctx.fillRect(0, 0, width, height)

  ctx.save()
  ctx.globalCompositeOperation = 'screen'
  const nebulaPalette = [
    ['rgba(68, 124, 205, 0.24)', 'rgba(68, 124, 205, 0)'],
    ['rgba(92, 151, 255, 0.18)', 'rgba(92, 151, 255, 0)'],
    ['rgba(157, 113, 214, 0.14)', 'rgba(157, 113, 214, 0)'],
    ['rgba(84, 208, 222, 0.12)', 'rgba(84, 208, 222, 0)'],
  ]
  for (let i = 0; i < 7; i += 1) {
    const seed = hashText(`nebula-${i}`)
    const drift = angle * (0.18 + (seed % 7) * 0.01)
    const x = centerX + Math.cos(seed * 0.017 + drift) * width * (0.16 + (seed % 23) / 190)
    const y = centerY + Math.sin(seed * 0.013 - drift * 0.7) * height * (0.12 + (seed % 19) / 210)
    const rx = width * (0.16 + (seed % 31) / 170)
    const ry = height * (0.06 + (seed % 29) / 260)
    const [inner, outer] = nebulaPalette[i % nebulaPalette.length]
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(-0.36 + (seed % 60) / 110)
    ctx.scale(1, ry / rx)
    const cloud = ctx.createRadialGradient(0, 0, 0, 0, 0, rx)
    cloud.addColorStop(0, inner)
    cloud.addColorStop(0.42, inner.replace('0.24', '0.11').replace('0.18', '0.09').replace('0.14', '0.07').replace('0.12', '0.06'))
    cloud.addColorStop(1, outer)
    ctx.fillStyle = cloud
    ctx.beginPath()
    ctx.arc(0, 0, rx, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()
  }
  ctx.restore()

  for (let i = 0; i < 360; i += 1) {
    const seed = i * 7919
    const parallax = 0.35 + (hashText(`p${seed}`) % 100) / 150
    const x = ((hashText(`x${seed}`) % Math.floor(width)) + Math.sin(time * 0.01 + seed) * parallax * 16 + time * 0.018 * parallax + width) % width
    const y = ((hashText(`y${seed}`) % Math.floor(height)) + Math.cos(time * 0.007 + seed) * parallax * 10 + height) % height
    const bright = hashText(`b${seed}`) % 100
    const r = bright > 94 ? 1.6 : bright > 82 ? 1.05 : 0.45 + (bright % 7) / 12
    const twinkle = 0.55 + Math.sin(time * 0.035 + seed) * 0.32
    ctx.fillStyle = bright > 88
      ? `rgba(255, 255, 255, ${0.62 + twinkle * 0.34})`
      : `rgba(187, 218, 255, ${0.12 + twinkle * 0.2 + (bright % 20) / 160})`
    ctx.beginPath()
    ctx.arc(x, y, r, 0, Math.PI * 2)
    ctx.fill()
    if (bright > 96) {
      ctx.strokeStyle = 'rgba(210, 232, 255, 0.32)'
      ctx.lineWidth = 0.7
      ctx.beginPath()
      ctx.moveTo(x - r * 3, y)
      ctx.lineTo(x + r * 3, y)
      ctx.moveTo(x, y - r * 3)
      ctx.lineTo(x, y + r * 3)
      ctx.stroke()
    }
  }

  ctx.save()
  ctx.globalCompositeOperation = 'screen'
  for (let layer = 0; layer < 3; layer += 1) {
    const count = layer === 0 ? 70 : layer === 1 ? 48 : 28
    const speed = 0.18 + layer * 0.22
    for (let i = 0; i < count; i += 1) {
      const seed = hashText(`field-${layer}-${i}`)
      const baseX = seed % Math.floor(width)
      const baseY = hashText(`field-y-${layer}-${i}`) % Math.floor(height)
      const driftX = (time * speed + seed * 0.017) % (width + 80)
      const driftY = Math.sin(time * 0.01 + seed) * (4 + layer * 5)
      const x = (baseX + driftX) % (width + 80) - 40
      const y = baseY + driftY
      const alpha = 0.08 + layer * 0.045 + ((seed % 30) / 300)
      const size = 0.7 + layer * 0.5 + (seed % 8) / 12
      const trail = 10 + layer * 9 + (seed % 12)
      const particle = ctx.createLinearGradient(x - trail, y + trail * 0.22, x, y)
      particle.addColorStop(0, 'rgba(120, 180, 255, 0)')
      particle.addColorStop(1, `rgba(210, 235, 255, ${alpha})`)
      ctx.strokeStyle = particle
      ctx.lineWidth = size
      ctx.beginPath()
      ctx.moveTo(x - trail, y + trail * 0.22)
      ctx.lineTo(x, y)
      ctx.stroke()
    }
  }
  for (let i = 0; i < 4; i += 1) {
    const seed = hashText(`meteor-${i}`)
    const cycle = ((time * (0.18 + i * 0.04) + seed) % 520) / 520
    if (cycle > 0.72) {
      const p = (cycle - 0.72) / 0.28
      const x = width * (0.08 + (seed % 70) / 100) + p * width * 0.32
      const y = height * (0.12 + (seed % 48) / 120) + p * height * 0.18
      const length = 80 + (seed % 70)
      const alpha = Math.sin(p * Math.PI) * 0.42
      const meteor = ctx.createLinearGradient(x - length, y + length * 0.28, x, y)
      meteor.addColorStop(0, 'rgba(255,255,255,0)')
      meteor.addColorStop(0.72, `rgba(140, 200, 255, ${alpha * 0.55})`)
      meteor.addColorStop(1, `rgba(255, 255, 255, ${alpha})`)
      ctx.strokeStyle = meteor
      ctx.lineWidth = 1.4
      ctx.beginPath()
      ctx.moveTo(x - length, y + length * 0.28)
      ctx.lineTo(x, y)
      ctx.stroke()
    }
  }
  ctx.restore()

  const galaxyTilt = -0.34
  const galaxyMajor = Math.min(width, height) * 0.68 * zoom
  const galaxyMinor = galaxyMajor * 0.3
  ctx.save()
  ctx.translate(centerX, centerY + height * 0.02)
  ctx.rotate(galaxyTilt)
  const disk = ctx.createRadialGradient(0, 0, 0, 0, 0, galaxyMajor)
  disk.addColorStop(0, 'rgba(255, 245, 222, 0.92)')
  disk.addColorStop(0.12, 'rgba(255, 231, 200, 0.62)')
  disk.addColorStop(0.28, 'rgba(172, 199, 230, 0.35)')
  disk.addColorStop(0.58, 'rgba(81, 118, 166, 0.22)')
  disk.addColorStop(1, 'rgba(8, 15, 32, 0)')
  ctx.scale(1, galaxyMinor / galaxyMajor)
  ctx.fillStyle = disk
  ctx.beginPath()
  ctx.arc(0, 0, galaxyMajor, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()

  ctx.save()
  ctx.translate(centerX, centerY + height * 0.02)
  ctx.rotate(galaxyTilt)
  for (let arm = 0; arm < 2; arm += 1) {
    for (let i = 0; i < 620; i += 1) {
      const t = i / 620
      const spin = arm * Math.PI + t * Math.PI * 5.9 + angle * 0.42
      const spread = ((hashText(`arm-${arm}-${i}`) % 100) - 50) / 100
      const radius = 18 + t * galaxyMajor * 1.08
      const x = Math.cos(spin) * radius + spread * 40
      const y = (Math.sin(spin) * radius * 0.24) + spread * 14
      const alpha = Math.max(0, 0.34 * (1 - t))
      const size = 0.45 + (hashText(`arm-size-${arm}-${i}`) % 16) / 10
      ctx.fillStyle = i % 5 === 0 ? `rgba(255, 244, 225, ${alpha})` : `rgba(166, 207, 255, ${alpha})`
      ctx.beginPath()
      ctx.arc(x, y, size, 0, Math.PI * 2)
      ctx.fill()
    }
  }
  ctx.filter = 'blur(9px)'
  const core = ctx.createRadialGradient(-8, -6, 0, 0, 0, 170)
  core.addColorStop(0, 'rgba(255, 255, 255, 1)')
  core.addColorStop(0.18, 'rgba(255, 252, 235, 0.98)')
  core.addColorStop(0.4, 'rgba(255, 226, 184, 0.68)')
  core.addColorStop(0.66, 'rgba(162, 196, 246, 0.34)')
  core.addColorStop(1, 'rgba(255, 255, 255, 0)')
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.ellipse(0, 0, 176, 86, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.globalCompositeOperation = 'screen'
  const coreDepth = ctx.createRadialGradient(-26, -20, 0, 0, 0, 128)
  coreDepth.addColorStop(0, 'rgba(255, 255, 255, 0.95)')
  coreDepth.addColorStop(0.28, 'rgba(255, 246, 218, 0.58)')
  coreDepth.addColorStop(0.62, 'rgba(110, 166, 245, 0.22)')
  coreDepth.addColorStop(1, 'rgba(255, 255, 255, 0)')
  ctx.fillStyle = coreDepth
  ctx.beginPath()
  ctx.arc(0, 0, 112, 0, Math.PI * 2)
  ctx.fill()
  const dreamHaze = ctx.createRadialGradient(0, 0, 0, 0, 0, 220)
  dreamHaze.addColorStop(0, 'rgba(255, 255, 255, 0.6)')
  dreamHaze.addColorStop(0.28, 'rgba(168, 210, 255, 0.26)')
  dreamHaze.addColorStop(0.62, 'rgba(159, 112, 220, 0.18)')
  dreamHaze.addColorStop(1, 'rgba(255, 255, 255, 0)')
  ctx.fillStyle = dreamHaze
  ctx.beginPath()
  ctx.ellipse(0, 0, 260, 110, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.filter = 'blur(16px)'
  const hotCore = ctx.createRadialGradient(-10, -8, 0, 0, 0, 82)
  hotCore.addColorStop(0, 'rgba(255, 255, 255, 1)')
  hotCore.addColorStop(0.52, 'rgba(255, 255, 246, 0.92)')
  hotCore.addColorStop(1, 'rgba(255, 236, 205, 0)')
  ctx.fillStyle = hotCore
  ctx.beginPath()
  ctx.arc(0, 0, 76, 0, Math.PI * 2)
  ctx.fill()
  ctx.filter = 'none'
  ctx.globalCompositeOperation = 'source-over'
  ctx.restore()

  ctx.save()
  ctx.globalCompositeOperation = 'lighter'
  ctx.translate(centerX, centerY + height * 0.02)
  ctx.rotate(galaxyTilt)
  for (let i = 0; i < 220; i += 1) {
    const seed = hashText(`dust-${i}`)
    const t = (seed % 1000) / 1000
    const orbit = Math.sqrt(t) * galaxyMajor * 1.1
    const spin = (seed % 628) / 100 + angle * (0.38 + (seed % 17) / 90)
    const wobble = Math.sin(angle * 2.1 + seed) * 7
    const x = Math.cos(spin) * orbit
    const y = Math.sin(spin) * orbit * 0.2 + wobble
    const size = 0.55 + (seed % 12) / 9
    const alpha = 0.12 + (1 - t) * 0.28
    ctx.fillStyle = i % 6 === 0 ? `rgba(255, 241, 210, ${alpha})` : `rgba(166, 213, 255, ${alpha})`
    ctx.beginPath()
    ctx.arc(x, y, size, 0, Math.PI * 2)
    ctx.fill()
    if (i % 11 === 0) {
      ctx.strokeStyle = `rgba(160, 208, 255, ${alpha * 0.24})`
      ctx.lineWidth = 0.7
      ctx.beginPath()
      ctx.moveTo(x - Math.sin(spin) * 9, y + Math.cos(spin) * 2)
      ctx.lineTo(x + Math.sin(spin) * 9, y - Math.cos(spin) * 2)
      ctx.stroke()
    }
  }
  ctx.restore()

  const edgeBlend = ctx.createRadialGradient(centerX, centerY, Math.min(width, height) * 0.22, centerX, centerY, Math.max(width, height) * 0.72)
  edgeBlend.addColorStop(0, 'rgba(0, 0, 0, 0)')
  edgeBlend.addColorStop(0.7, 'rgba(4, 9, 22, 0.18)')
  edgeBlend.addColorStop(1, 'rgba(2, 3, 10, 0.78)')
  ctx.fillStyle = edgeBlend
  ctx.fillRect(0, 0, width, height)
  const topMist = ctx.createLinearGradient(0, 0, 0, height)
  topMist.addColorStop(0, 'rgba(60, 92, 150, 0.16)')
  topMist.addColorStop(0.18, 'rgba(20, 35, 72, 0.08)')
  topMist.addColorStop(0.78, 'rgba(0, 0, 0, 0)')
  topMist.addColorStop(1, 'rgba(9, 13, 26, 0.32)')
  ctx.fillStyle = topMist
  ctx.fillRect(0, 0, width, height)

  const rotate = (node: any) => {
    const cos = Math.cos(angle)
    const sin = Math.sin(angle)
    let sourceX = node.x
    let sourceY = node.y
    let sourceZ = node.z
    if (node.focusMode) {
      if (node.isCenter) {
        sourceX = Math.sin(angle * 1.5) * 4
        sourceY = Math.cos(angle * 1.1) * 3
        sourceZ = Math.cos(angle * 1.3) * 4
      } else {
        const phase = node.orbitPhase + angle * (node.orbitSpeed || 0.25)
        const wave = Math.sin(phase * 1.7 + angle) * (node.isRelated ? 18 : 34)
        sourceX = Math.cos(phase) * node.orbitRadius
        sourceZ = Math.sin(phase) * node.orbitRadius
        sourceY = node.y * 0.58 + wave
      }
    }
    const x = sourceX * cos - sourceZ * sin
    const z = sourceX * sin + sourceZ * cos
    const perspective = camera / (camera + z * zoom + 150)
    return {
      ...node,
      px: centerX + x * perspective * scaleBase,
      py: centerY + node.y * perspective * scaleBase,
      pz: z,
      perspective,
    }
  }

  for (const node of nodes) projected.set(node.tag, rotate(node))

  for (const link of links) {
    const a = projected.get(link.source)
    const b = projected.get(link.target)
    if (!a || !b) continue
    const selectedLink = activeGalaxyTag.value && (link.source === activeGalaxyTag.value || link.target === activeGalaxyTag.value)
    const dimUnrelated = activeGalaxyTag.value && !selectedLink
    const alpha = dimUnrelated
      ? Math.min(0.12, 0.035 + Number(link.weight || 1) * 0.018)
      : Math.min(0.58, 0.14 + Number(link.weight || 1) * 0.065)
    const beam = ctx.createLinearGradient(a.px, a.py, b.px, b.py)
    beam.addColorStop(0, `rgba(180, 220, 255, ${alpha})`)
    beam.addColorStop(0.5, `rgba(255, 255, 255, ${alpha * 0.72})`)
    beam.addColorStop(1, `rgba(115, 179, 255, ${alpha})`)
    ctx.strokeStyle = beam
    ctx.lineWidth = Math.max(0.8, Math.min(4.2, link.weight)) * ((a.perspective + b.perspective) / 2) * (selectedLink ? 1.28 : 1)
    ctx.shadowColor = selectedLink ? 'rgba(190, 230, 255, 0.42)' : 'rgba(100, 170, 255, 0.2)'
    ctx.shadowBlur = selectedLink ? 14 : 7
    ctx.beginPath()
    ctx.moveTo(a.px, a.py)
    ctx.lineTo(b.px, b.py)
    ctx.stroke()
    ctx.shadowBlur = 0
  }

  const targets: { tag: string; x: number; y: number; radius: number }[] = []
  Array.from(projected.values()).sort((a, b) => a.pz - b.pz).forEach((node: any) => {
    const active = activeGalaxyTag.value === node.tag
    const related = Boolean(activeGalaxyTag.value && node.isRelated)
    const unrelated = Boolean(activeGalaxyTag.value && !active && !related)
    const pulse = 0.86 + Math.sin(time * 0.026 + hashText(node.tag)) * 0.14
    const radius = (7 + Math.min(12, node.count * 2.4)) * node.perspective * (active ? 1.42 : related ? 1.16 : 0.9) * pulse
    const haloRadius = radius * (active ? 2.8 : 2.25)
    const star = ctx.createRadialGradient(node.px, node.py, 0, node.px, node.py, haloRadius)
    star.addColorStop(0, '#ffffff')
    star.addColorStop(0.12, active ? 'rgba(250,255,242,0.98)' : related ? 'rgba(234,246,255,0.92)' : 'rgba(234,246,255,0.62)')
    star.addColorStop(0.42, active ? 'rgba(130, 255, 205, 0.42)' : related ? `hsla(${node.hue}, 90%, 66%, 0.34)` : `hsla(${node.hue}, 70%, 62%, 0.16)`)
    star.addColorStop(1, 'rgba(255, 255, 255, 0)')
    ctx.shadowColor = active ? 'rgba(177, 255, 221, 0.52)' : 'rgba(132, 194, 255, 0.28)'
    ctx.shadowBlur = active ? 18 : 10
    ctx.fillStyle = star
    ctx.beginPath()
    ctx.arc(node.px, node.py, haloRadius, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = active ? 'rgba(235, 255, 245, 0.92)' : 'rgba(221, 239, 255, 0.78)'
    ctx.beginPath()
    ctx.arc(node.px, node.py, Math.max(1.2, radius * 0.24), 0, Math.PI * 2)
    ctx.fill()
    ctx.strokeStyle = active ? 'rgba(226, 255, 240, 0.34)' : 'rgba(210, 232, 255, 0.2)'
    ctx.lineWidth = 0.7
    ctx.beginPath()
    ctx.moveTo(node.px - radius * 1.15, node.py)
    ctx.lineTo(node.px + radius * 1.15, node.py)
    ctx.moveTo(node.px, node.py - radius * 1.15)
    ctx.lineTo(node.px, node.py + radius * 1.15)
    ctx.stroke()
    ctx.shadowBlur = 0
    ctx.globalAlpha = unrelated ? 0.46 : 1
    ctx.fillStyle = active ? 'rgba(255,255,255,0.94)' : related ? 'rgba(236, 246, 255, 0.82)' : 'rgba(216, 232, 255, 0.56)'
    ctx.font = `${Math.max(11, 12 * node.perspective)}px system-ui, sans-serif`
    ctx.textAlign = 'center'
    ctx.shadowColor = 'rgba(0, 0, 0, 0.82)'
    ctx.shadowBlur = 5
    ctx.fillText(node.tag, node.px, node.py + radius + 15)
    ctx.fillStyle = active ? '#b8ffd9' : 'rgba(185, 215, 255, 0.88)'
    ctx.font = `${Math.max(9, 10 * node.perspective)}px system-ui, sans-serif`
    ctx.fillText(`${node.count}题`, node.px, node.py + radius + 28)
    ctx.globalAlpha = 1
    ctx.shadowBlur = 0
    targets.push({ tag: node.tag, x: node.px, y: node.py, radius: radius + 18 })
  })
  galaxyTargets.value = targets
  if (!reducedMotion) galaxyFrame = window.requestAnimationFrame(drawTagGalaxy)
}

function onGalaxyClick(event: MouseEvent) {
  const rect = galaxyCanvas.value?.getBoundingClientRect()
  if (!rect) return
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top
  const target = galaxyTargets.value.find((item) => Math.hypot(item.x - x, item.y - y) <= item.radius)
  if (target) {
    activeGalaxyTag.value = target.tag
    galaxyInteractionStatus.value = `已选择错题标签${target.tag}。`
  }
}

function onGalaxyPointerMove(event: MouseEvent) {
  const rect = galaxyCanvas.value?.getBoundingClientRect()
  if (!rect) return
  galaxyMouse.active = true
  galaxyMouse.targetX = Math.max(-1, Math.min(1, ((event.clientX - rect.left) / rect.width - 0.5) * 2))
  galaxyMouse.targetY = Math.max(-1, Math.min(1, ((event.clientY - rect.top) / rect.height - 0.5) * 2))
}

function onGalaxyPointerLeave() {
  galaxyMouse.active = false
  galaxyMouse.targetX = 0
  galaxyMouse.targetY = 0
}

function onGalaxyWheel(event: WheelEvent) {
  setGalaxyZoom(galaxyZoom.value + (event.deltaY > 0 ? -GALAXY_ZOOM_STEP : GALAXY_ZOOM_STEP), false)
}

function setGalaxyZoom(value: number, announce = true) {
  galaxyZoom.value = Math.max(GALAXY_ZOOM_MIN, Math.min(GALAXY_ZOOM_MAX, Number(value.toFixed(2))))
  if (announce) galaxyInteractionStatus.value = `错题标签星系缩放至${Math.round(galaxyZoom.value * 100)}%。`
}

function resetGalaxyZoom() {
  setGalaxyZoom(1)
}

function handleGalaxyKeydown(event: KeyboardEvent) {
  if (event.key === '+' || event.key === '=') {
    event.preventDefault()
    setGalaxyZoom(galaxyZoom.value + GALAXY_ZOOM_STEP)
    return
  }
  if (event.key === '-' || event.key === '_') {
    event.preventDefault()
    setGalaxyZoom(galaxyZoom.value - GALAXY_ZOOM_STEP)
    return
  }
  if (event.key === '0') {
    event.preventDefault()
    resetGalaxyZoom()
    return
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    activeGalaxyTag.value = ''
    galaxyInteractionStatus.value = '已清除当前错题标签。'
  }
}

const activeGalaxyNode = computed(() => {
  return tagGalaxy.value.nodes.find((node: any) => node.tag === activeGalaxyTag.value) || tagGalaxy.value.nodes[0] || null
})

function isMultipleQuestion(question: any) {
  const type = String(question?.type || '').toLowerCase()
  return type === 'multiple_choice' || type.includes('multiple') || type.includes('多选')
}

function answerKeys(value = redoAnswer.value) {
  return String(value || '').split(/[,，、\s]+/).map((item) => item.trim().toUpperCase()).filter(Boolean)
}

function isRedoOptionSelected(key: string) {
  return currentRedoIsMultiple.value ? answerKeys().includes(key) : redoAnswer.value === key
}

function onRedoOptionChange(key: string, event: Event) {
  if (currentRedoIsMultiple.value) {
    const checked = Boolean((event.target as HTMLInputElement | null)?.checked)
    const keys = new Set(answerKeys())
    if (checked) keys.add(key)
    else keys.delete(key)
    redoAnswer.value = Array.from(keys).sort().join(',')
    return
  }
  redoAnswer.value = key
}

function recordKey(record: any) {
  return String(record?.question_id || record?.stem || record?.id || '')
}

function toggleWrongRecordSelection(record: any, checked: boolean) {
  const id = String(record?.id || '')
  if (!id) return
  if (checked) {
    if (!selectedWrongRecordIds.value.includes(id)) selectedWrongRecordIds.value = [...selectedWrongRecordIds.value, id]
  } else {
    selectedWrongRecordIds.value = selectedWrongRecordIds.value.filter((item) => item !== id)
  }
}

function onWrongRecordSelection(record: any, event: Event) {
  toggleWrongRecordSelection(record, Boolean((event.target as HTMLInputElement | null)?.checked))
}

function toggleSelectCourseWrongRecords(course: any) {
  const ids = (course.items || []).map((item: any) => String(item.id)).filter(Boolean)
  const selected = new Set(selectedWrongRecordIds.value)
  const everySelected = ids.length && ids.every((id: string) => selected.has(id))
  selectedWrongRecordIds.value = everySelected
    ? selectedWrongRecordIds.value.filter((id) => !ids.includes(id))
    : Array.from(new Set([...selectedWrongRecordIds.value, ...ids]))
}

async function submitRedo() {
  if (!currentRedoRecord.value || !redoAnswer.value || redoSession.value?.completed) return
  const resp = await fetch('/api/exercise/answer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ student_id: studentId.value, question_id: currentRedoRecord.value.question_id, answer: redoAnswer.value }),
  })
  const payload = await resp.json()
  if (payload.success) {
    redoResult.value = payload.data
    onExerciseAnswered(payload.data)
    if (redoSession.value) {
      if (payload.data.correct) redoSession.value.correct += 1
      else redoSession.value.wrong += 1
    }
    if (payload.data.correct) {
      recordMasteredGalaxyStar(currentRedoRecord.value)
      await deleteWrongRecord(currentRedoRecord.value, false)
    } else {
      await loadWrongBook()
    }
  } else {
    wrongBookError.value = payload.error?.message || '重做判题失败'
  }
}

async function nextRedoQuestion() {
  if (!redoSession.value) return
  if (redoSession.value.index >= redoSession.value.queue.length - 1) {
    redoSession.value.completed = true
    await loadWrongBook()
    return
  }
  redoSession.value.index += 1
  redoAnswer.value = ''
  redoResult.value = null
}

function selectRedoQuestion(index: number) {
  if (!redoSession.value || index < 0 || index >= redoSession.value.queue.length) return
  redoSession.value.index = index
  redoAnswer.value = ''
  redoResult.value = null
}

async function finishRedoSession() {
  redoSession.value = null
  redoAnswer.value = ''
  redoResult.value = null
  await loadWrongBook()
}

async function deleteWrongRecord(record: any, reload = true) {
  const resp = await fetch(`/api/exercise/wrong-book/${encodeURIComponent(record.id)}?student_id=${encodeURIComponent(studentId.value)}`, {
    method: 'DELETE',
  })
  const payload = await resp.json()
  if (payload.success) {
    wrongBook.value = payload.data
    selectedWrongRecordIds.value = selectedWrongRecordIds.value.filter((id) => id !== String(record.id))
    if (reload) await loadWrongBook()
  } else {
    wrongBookError.value = payload.error?.message || '删除错题失败'
  }
}

async function deleteAllWrongRecords() {
  if (!wrongBookStats.value.totalWrong) return
  const resp = await fetch(`/api/exercise/wrong-book?student_id=${encodeURIComponent(studentId.value)}`, {
    method: 'DELETE',
  })
  const payload = await resp.json()
  if (payload.success) {
    wrongBook.value = payload.data || emptyWrongBookData()
    selectedWrongRecordIds.value = []
    await finishRedoSession()
  } else {
    wrongBookError.value = payload.error?.message || '一键删除错题失败'
  }
}

async function deleteSelectedWrongRecords() {
  const records = [...selectedWrongRecords.value]
  if (!records.length) return
  for (const record of records) {
    await deleteWrongRecord(record, false)
  }
  selectedWrongRecordIds.value = []
  await loadWrongBook()
}

function onExerciseAnswered(payload?: any) {
  applyExerciseRadarImpact(payload)
  void loadWrongBook()
  const progress = payload?.path_progress
  if (!progress || !currentPathStage.value) return
  currentPathStage.value = {
    ...currentPathStage.value,
    status: progress.status,
    mastery: progress.mastery,
    answered_count: progress.answered_count,
    correct_count: progress.correct_count,
    target_count: progress.target_count,
    accuracy: progress.accuracy,
  }
  closedLoopStatus.value = progress.message || `当前阶段掌握度已更新为 ${progress.mastery}% 。`
  if (progress.advanced) {
    window.setTimeout(async () => {
      await loadPathContext()
      setActiveQuestionBankIds([])
      resources.value = []
      activePage.value = 'builder'
      closedLoopStatus.value = progress.next_stage_id
        ? '上一阶段已达标，下一阶段已自动解锁。请定制新阶段题库后继续。'
        : '全部路径阶段已完成。'
    }, 1200)
  }
}

function normalizeOptions(options: string[]) {
  const seen = new Set<string>()
  return options
    .flatMap((option) => {
      const text = String(option || '').trim()
      const matches = [...text.matchAll(/(?<![A-Za-z])([A-Ha-h])(?:[.、．]?\s*)/g)]
      if (matches.length <= 1) return [text]
      return matches.map((match, index) => text.slice(match.index || 0, matches[index + 1]?.index ?? text.length).trim())
    })
    .filter(Boolean)
    .map((option) => {
      const match = option.match(/^([A-Ha-h])(?:[.、．]?\s*)?(.*)$/)
      return { text: (match?.[2] || option).trim(), raw: option }
    })
    .filter((option) => {
      const fingerprint = option.text.replace(/\s+/g, '').toLowerCase()
      if (!fingerprint || seen.has(fingerprint)) return false
      seen.add(fingerprint)
      return true
    })
    .map((option, index) => ({ ...option, key: String.fromCharCode(65 + index) }))
}

function radarPoint(index: number, score: number, radius = 84) {
  const count = Math.max(1, abilityRadar.value.length)
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / count
  const distance = radius * Math.max(0, Math.min(100, score)) / 100
  return `${120 + Math.cos(angle) * distance},${120 + Math.sin(angle) * distance}`
}

function radarAxisPoint(index: number, radius = 92) {
  const count = Math.max(1, abilityRadar.value.length)
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / count
  return { x: 120 + Math.cos(angle) * radius, y: 120 + Math.sin(angle) * radius }
}

function radarLabelPoint(index: number, radius = 112) {
  const count = Math.max(1, abilityRadar.value.length)
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / count
  return { x: 120 + Math.cos(angle) * radius, y: 120 + Math.sin(angle) * radius }
}

watch(activePage, async (page) => {
  if (page === 'wrongBook') await loadWrongBook()
  if (page === 'tagGalaxy') {
    await loadWrongBook()
    if (activePage.value !== 'tagGalaxy') return
    await nextTick()
    startTagGalaxy()
  } else {
    stopTagGalaxy()
  }
})

watch(studentId, async () => {
  await loadPathContext()
  await restoreActiveQuestionBanks()
})

watch(() => [
  tagGalaxy.value.nodes.map((node: any) => `${node.tag}:${node.count}`).join('|'),
  tagGalaxy.value.links.map((link: any) => `${link.source}-${link.target}:${link.weight}`).join('|'),
].join('::'), () => {
  if (!activeGalaxyTag.value && tagGalaxy.value.nodes.length) activeGalaxyTag.value = tagGalaxy.value.nodes[0].tag
  if (activePage.value === 'tagGalaxy') void nextTick(startTagGalaxy)
})

watch(activeGalaxyTag, () => {
  if (activePage.value === 'tagGalaxy') {
    if (!refreshGalaxyFocusState()) {
      galaxyNeedsRebuild = true
      void nextTick(startTagGalaxy)
    }
  }
})

onMounted(async () => {
  loadMasteredGalaxyStars()
  void loadWrongBook()
  await loadPathContext()
  await restoreActiveQuestionBanks()
  if (shouldAutoStartStageBank.value && currentPathStage.value && !activeQuestionBankIds.value.length) {
    await generateFromCustomize()
  }
})

onBeforeUnmount(() => {
  stopTagGalaxy()
  if (galaxyRefreshFeedbackTimer !== null) window.clearTimeout(galaxyRefreshFeedbackTimer)
  disposeTagGalaxyScene()
  galaxyRenderer?.dispose?.()
  galaxyRenderer = null
})
</script>

<template>
  <div class="studio-page workshop-shell workshop-shell-practice">
    <aside class="workshop-sidebar studio-panel">
      <div class="workshop-sidebar-head practice-workshop-head">
        <span class="practice-workshop-eyebrow">Practice Center</span>
        <strong class="practice-workshop-title">练习诊断中心</strong>
        <p>智能练习 · 精准诊断 · 个性提升</p>
      </div>
      <nav class="workshop-nav practice-workshop-nav" aria-label="练习诊断导航">
        <button type="button" :class="{ active: activePage === 'builder' }" @click="trySwitchPage('builder')">
          <span class="practice-workshop-icon">▤</span>
          <span class="practice-workshop-copy">
            <strong>题库定制</strong>
            <small>按路径阶段设置难度、数量与题型</small>
          </span>
        </button>
        <button type="button" :class="{ active: activePage === 'diagnosis' }" @click="trySwitchPage('diagnosis')">
          <span class="practice-workshop-icon">✓</span>
          <span class="practice-workshop-copy">
            <strong>智能做题</strong>
            <small>训练、考试与即时诊断</small>
          </span>
        </button>
        <button type="button" :class="{ active: activePage === 'wrongBook' }" @click="trySwitchPage('wrongBook')">
          <span class="practice-workshop-icon">▧</span>
          <span class="practice-workshop-copy">
            <strong>错题本</strong>
            <small>复盘、重做与错因沉淀</small>
          </span>
        </button>
        <button type="button" :class="{ active: activePage === 'tagGalaxy' }" @click="trySwitchPage('tagGalaxy')">
          <span class="practice-workshop-icon">◎</span>
          <span class="practice-workshop-copy">
            <strong>知识点诊断</strong>
            <small>薄弱标签与能力分布</small>
          </span>
        </button>
      </nav>
      <div class="workshop-summary practice-learning-card">
        <span class="practice-learning-label">正在学习</span>
        <strong>{{ pathStageTitle }}</strong>
        <p>{{ pathCourseTitle }}</p>
        <div class="practice-learning-progress" aria-hidden="true">
          <i :style="{ width: activeQuestionBankIds.length ? `${Math.min(100, Math.max(14, activeExerciseQuestionLimit * 5))}%` : '0%' }"></i>
        </div>
        <div class="practice-learning-meta">
          <span>掌握度 {{ pathStageMastery }}%</span>
          <em>{{ activeQuestionBankIds.length ? pathStageProgressText : '暂无阶段题库' }}</em>
        </div>
        <button type="button" :disabled="activePage === 'builder'" @click="trySwitchPage('builder')">{{ activePage === 'builder' ? '正在调整阶段题库' : '调整阶段题库' }}</button>
      </div>
    </aside>

    <main class="workshop-content">
      <section v-if="false" class="studio-panel" aria-hidden="true">
        <div class="studio-panel-header">
          <div>
            <div class="studio-title"><span class="studio-title-dot"></span>专业课程选择</div>
            <p>先选择专业大类、小类和课程目录；如果选择其它，课程类别和课程内容会同步进入自定义模式。</p>
          </div>
          <div class="studio-actions">
            <button class="studio-btn ghost" @click="resetCourseWorkflow">重新选择</button>
            <button class="studio-btn secondary" @click="goCustomize">进入出题定制</button>
          </div>
        </div>
        <div class="studio-panel-body">
          <div v-if="courseLocked" class="studio-empty mb-3">专业课程已确定，后续题库、训练和错题归档都会沿用该选择。</div>
          <div class="studio-grid studio-grid-balanced">
            <label class="grid gap-2">
              <span class="text-sm font-black text-slate-700">专业大类</span>
              <select v-model="selectedMajorCategory" class="studio-select" :disabled="courseLocked" @change="syncMajorCategory">
                <option v-for="item in majorCatalog" :key="item.category" :value="item.category">{{ item.category }}</option>
              </select>
            </label>
            <label class="grid gap-2">
              <span class="text-sm font-black text-slate-700">专业小类</span>
              <select v-model="selectedMajor" class="studio-select" :disabled="courseLocked" @change="syncMajor">
                <option v-for="major in majorOptions" :key="major" :value="major">{{ major }}</option>
              </select>
            </label>
          </div>
          <input v-if="selectedMajor === '其它'" v-model="customMajor" class="studio-input mt-3" :disabled="courseLocked" placeholder="请输入专业名称" @input="syncCustomizationDefaults" />

          <div class="studio-grid studio-grid-balanced mt-4">
            <label class="grid gap-2">
              <span class="text-sm font-black text-slate-700">课程大类</span>
              <select v-model="selectedCourseCategory" class="studio-select" :disabled="courseLocked" @change="syncCourse">
                <option v-for="item in courseCatalog" :key="item.category" :value="item.category">{{ item.category }}</option>
              </select>
            </label>
            <label class="grid gap-2">
              <span class="text-sm font-black text-slate-700">课程内容</span>
              <select v-model="selectedCourse" class="studio-select" :disabled="courseLocked" @change="syncCustomizationDefaults">
                <option v-for="course in courseOptions" :key="course" :value="course">{{ course }}</option>
              </select>
            </label>
          </div>
          <div v-if="selectedCourseCategory === '其它' || selectedCourse === '其它'" class="studio-grid studio-grid-balanced mt-3">
            <input v-if="selectedCourseCategory === '其它'" v-model="customCourseCategory" class="studio-input" :disabled="courseLocked" placeholder="请输入课程类别" @input="syncCustomizationDefaults" />
            <input v-if="selectedCourse === '其它'" v-model="customCourse" class="studio-input" :disabled="courseLocked" placeholder="请输入课程内容" @input="syncCustomizationDefaults" />
          </div>

          <section class="practice-config-summary" aria-label="当前训练配置">
            <div class="practice-config-summary__head">
              <div>
                <span>当前训练配置</span>
                <strong>课程选择将直接约束定制题库</strong>
              </div>
              <button class="studio-btn secondary" type="button" @click="goCustomize">继续定制</button>
            </div>
            <div class="practice-config-summary__grid">
              <article>
                <span>专业方向</span>
                <strong>{{ effectiveMajor }}</strong>
                <small>{{ selectedMajorCategory }}</small>
              </article>
              <article>
                <span>当前课程</span>
                <strong>{{ effectiveCourse }}</strong>
                <small>{{ effectiveCourseCategory }}</small>
              </article>
              <article>
                <span>诊断焦点</span>
                <strong>{{ specificKnowledgePoint || '待设置知识点' }}</strong>
                <small>进入出题定制后可修改</small>
              </article>
              <article>
                <span>题库规格</span>
                <strong>{{ totalQuestionCount }} 题 · {{ questionDifficultyLabel }}</strong>
                <small>{{ selectedQuestionTypes.length }} 种题型已启用</small>
              </article>
            </div>
          </section>

          <div class="stage-steps mt-4">
            <div class="stage-step">
              <div class="stage-step-num">1</div>
              <div>
                <strong>专业课程定位</strong>
                <p>当前选择会作为题库生成的学科上下文，影响知识点范围、案例背景和难度表达。</p>
              </div>
              <button class="studio-btn secondary" @click="goCustomize">下一步</button>
            </div>
            <div class="stage-step">
              <div class="stage-step-num">2</div>
              <div>
                <strong>错题与诊断联动</strong>
                <p>也可以直接进入错题本，从历史错误反推薄弱点，再回到出题定制生成针对性题库。</p>
              </div>
              <button class="studio-btn ghost" @click="trySwitchPage('wrongBook')">查看错题本</button>
            </div>
          </div>
        </div>
      </section>

      <section v-show="activePage === 'builder'" class="studio-panel">
        <div class="studio-panel-header">
          <div>
            <div class="studio-title"><span class="studio-title-dot green"></span>路径题库定制</div>
            <p>题目只来自当前学习节点；你可以定制难度、数量和题型，完成后系统自动更新掌握度并判定是否晋级。</p>
          </div>
          <div class="studio-actions">
            <button class="studio-btn" :disabled="generating || totalQuestionCount <= 0 || !currentPathStage" @click="generateFromCustomize">
              {{ generating ? '题库生成中' : '生成阶段题库并开始' }}
            </button>
          </div>
        </div>
        <div class="studio-panel-body">
          <div class="grid gap-3">
            <section v-if="currentPathStage" class="practice-config-summary" aria-label="当前路径阶段">
              <div class="practice-config-summary__head">
                <div>
                  <span>当前路径阶段</span>
                  <strong>{{ pathStageTitle }}</strong>
                </div>
                <span class="cp-status">{{ currentPathStage.status === 'warning' ? '需补强' : '正在学习' }}</span>
              </div>
              <div class="practice-config-summary__grid">
                <article><span>所属路径</span><strong>{{ pathCourseTitle }}</strong><small>题目不会跨出该节点</small></article>
                <article><span>阶段目标</span><strong>{{ pathStageGoal }}</strong><small>{{ currentPathStage.checkpoint || '完成测试形成学习证据' }}</small></article>
                <article><span>当前掌握度</span><strong>{{ pathStageMastery }}%</strong><small>每次提交后实时更新</small></article>
                <article><span>自动晋级</span><strong>掌握度 ≥ 80%</strong><small>完成本轮全部题目后判定</small></article>
              </div>
            </section>
            <div v-else class="studio-empty">{{ pathContextLoading ? '正在读取当前路径阶段…' : '没有可用路径阶段，请先前往路径推送生成学习路径。' }}</div>
            <div class="studio-grid studio-grid-balanced">
              <label class="grid gap-2">
                <span class="text-sm font-black text-slate-700">题目总数</span>
                <input class="studio-input" type="number" :value="totalQuestionCount" readonly />
              </label>
              <label class="grid gap-2">
                <span class="text-sm font-black text-slate-700">题目难度</span>
                <select v-model="questionDifficulty" class="studio-select" @change="applyQuizConfig">
                  <option value="mixed">由易到难混合</option>
                  <option value="easy">基础巩固</option>
                  <option value="medium">中等应用</option>
                  <option value="hard">综合提升</option>
                </select>
              </label>
            </div>
            <div class="grid gap-2">
              <span class="text-sm font-black text-slate-700">题型数量</span>
              <div class="question-type-grid">
                <label v-for="type in questionTypeOptions" :key="type.value" class="question-type-card">
                  <span>
                    <strong>{{ type.label }}</strong>
                    <em>{{ type.hint }}</em>
                  </span>
                  <input
                    v-model.number="questionTypeCounts[type.value]"
                    type="number"
                    min="0"
                    max="20"
                    @change="applyQuizConfig"
                  />
                </label>
              </div>
            </div>
            <p class="studio-muted">当前身份：{{ studentId }}。题库只使用“{{ pathStageTitle }}”的目标与验收标准作为出题上下文。</p>
            <div class="studio-actions">
              <button class="studio-btn" :disabled="generating || totalQuestionCount <= 0 || !currentPathStage" @click="generateFromCustomize">
                {{ generating ? '题库生成中' : '生成阶段题库并开始学习' }}
              </button>
              <button class="studio-btn ghost" @click="trySwitchPage('wrongBook')">从错题本调整</button>
            </div>
            <div v-if="error" class="text-sm font-bold text-orange-600">{{ error }}</div>
          </div>
        </div>
      </section>

      <section
        v-show="activePage === 'wrongBook'"
        class="studio-panel"
        :class="{ 'wrongbook-panel-empty': !wrongBookStats.totalWrong && !redoSession }"
      >
        <div class="studio-panel-header">
          <div>
            <div class="studio-title"><span class="studio-title-dot green"></span>错题本</div>
            <p>按专业和课程整理错题文件夹，错题标签会进入能力雷达；每次训练和重做都会动态更新。</p>
          </div>
          <div v-if="!redoSession" class="studio-actions">
            <span v-if="selectedWrongRecordIds.length" class="wrongbook-selection-pill">已选 {{ selectedWrongRecordIds.length }} 题</span>
            <button v-if="wrongBookStats.totalWrong" class="studio-btn secondary" @click="openRedoAll">{{ redoAllButtonText }}</button>
            <button v-if="wrongBookStats.totalWrong" class="studio-btn danger" :disabled="!selectedWrongRecordIds.length" @click="deleteSelectedWrongRecords">批量删除</button>
            <button v-if="wrongBookStats.totalWrong" class="studio-btn danger" @click="deleteAllWrongRecords">一键删除错题</button>
            <button class="studio-btn ghost" :disabled="wrongBookLoading" @click="loadWrongBook">{{ wrongBookLoading ? '刷新中' : '刷新错题本' }}</button>
          </div>
        </div>
        <div class="studio-panel-body">
          <section v-if="redoSession" class="wrongbook-redo-workbench">
            <aside v-if="redoSession.queue.length" class="wrongbook-hover-directory" aria-label="重做错题目录">
              <span class="wrongbook-hover-tab">目录</span>
              <div class="wrongbook-hover-panel">
                <strong>重做目录</strong>
                <button
                  v-for="(item, idx) in redoSession.queue"
                  :key="`redo-nav-${item.id || item.question_id || idx}`"
                  type="button"
                  :class="{ active: idx === redoSession.index }"
                  @click="selectRedoQuestion(idx)"
                >
                  <span>{{ idx + 1 }}. {{ item.stem }}</span>
                  <em>{{ item.type || '题目' }}</em>
                </button>
              </div>
            </aside>
            <div class="wrongbook-redo-head">
              <div>
                <div class="studio-title"><span class="studio-title-dot"></span>错题重做训练</div>
                <p>{{ redoSession.title }} · {{ redoSession.index + 1 }} / {{ redoSession.queue.length }}</p>
              </div>
              <div class="studio-actions">
                <button class="studio-btn ghost" @click="finishRedoSession">结束重做</button>
              </div>
            </div>

            <div v-if="redoSession.completed" class="wrongbook-redo-summary">
              <strong>本轮错题重做完成</strong>
              <span>答对 {{ redoSession.correct }} 题，仍需复盘 {{ redoSession.wrong }} 题。</span>
              <button class="studio-btn" @click="finishRedoSession">回到错题本</button>
            </div>

            <template v-else>
              <article class="exercise-question mt-3">
                <strong>{{ currentRedoRecord?.stem }}</strong>
                <div class="exercise-tags">
                  <span v-for="tag in currentRedoRecord?.tags || []" :key="tag">{{ tag }}</span>
                </div>
                <p class="studio-muted mt-3">原答案：{{ currentRedoRecord?.answer || '未记录' }}；正确答案：{{ currentRedoRecord?.correct_answer || '待核验' }}</p>
              </article>
              <div v-if="redoOptions.length" class="exercise-options mt-3">
                <label v-for="option in redoOptions" :key="option.key" :class="{ selected: isRedoOptionSelected(option.key) }">
                  <input
                    :type="currentRedoIsMultiple ? 'checkbox' : 'radio'"
                    :name="currentRedoRecord?.id || currentRedoRecord?.question_id"
                    :value="option.key"
                    :checked="isRedoOptionSelected(option.key)"
                    @change="onRedoOptionChange(option.key, $event)"
                  />
                  <span class="exercise-option-key">{{ option.key }}</span>
                  <span class="exercise-option-text">{{ option.text }}</span>
                </label>
              </div>
              <input v-else v-model="redoAnswer" class="exercise-answer-input mt-3" placeholder="输入重做答案" />
              <div class="studio-actions mt-3">
                <button class="studio-btn" :disabled="!redoAnswer || !!redoResult" @click="submitRedo">提交重做</button>
                <button v-if="redoResult" class="studio-btn secondary" @click="nextRedoQuestion">
                  {{ redoSession.index >= redoSession.queue.length - 1 ? '完成本轮' : '下一题' }}
                </button>
              </div>
              <div v-if="redoResult" class="exercise-result mt-3" :class="redoResult.correct ? 'is-correct' : 'is-wrong'">
                <strong>{{ redoResult.correct ? '重做正确，已从错题本移除' : '重做仍需复盘' }}</strong>
                <span>正确答案：{{ redoResult.correct_answer || '待核验' }}</span>
                <p v-if="redoResult.analysis">{{ redoResult.analysis }}</p>
              </div>
            </template>
          </section>

          <template v-else-if="wrongBookStats.totalWrong">
          <div class="wrongbook-stats">
            <div>
              <strong>{{ wrongBookStats.totalWrong }}</strong>
              <span>仍需复盘错题</span>
            </div>
            <div>
              <strong>{{ wrongBookStats.courseCount }}</strong>
              <span>涉及课程文件夹</span>
            </div>
            <div>
              <strong>{{ masteredGalaxyStars.length }}</strong>
              <span>历史星</span>
            </div>
          </div>
          <section class="wrongbook-history-entry">
            <div>
              <strong>历史星系</strong>
              <span>重做正确的错题会沉淀为高亮历史星，训练诊断会同步影响能力雷达。</span>
            </div>
            <button class="studio-btn secondary" type="button" @click="openTagGalaxy()">进入历史星系</button>
          </section>
          <section class="wrongbook-folder-directory">
            <div class="wrongbook-directory-head">
              <strong>课程文件夹</strong>
              <div class="studio-actions">
                <button class="studio-btn ghost" @click="toggleAllCourseFolders">{{ allCourseFoldersOpen ? '收起全部' : '展开全部' }}</button>
              </div>
            </div>
            <div v-if="!courseFolders.length" class="studio-empty">暂无课程文件夹。</div>
            <button
              v-for="folder in courseFolders"
              :key="folder.key"
              type="button"
              :class="{ active: openCourseFolders[folder.key] }"
              @click="toggleCourseFolder(folder.major, folder.course)"
            >
              <span>{{ folder.major }} / {{ folder.course }}</span>
              <strong>{{ folder.count }} 题</strong>
            </button>
          </section>
          <div class="wrongbook-layout">
            <section class="wrongbook-radar">
              <div class="studio-title"><span class="studio-title-dot green"></span>能力雷达图</div>
              <svg :key="radarSignature" class="ability-radar-svg" viewBox="0 0 240 240" role="img" aria-label="能力雷达图">
                <polygon points="120,36 192.7,78 192.7,162 120,204 47.3,162 47.3,78" class="radar-grid" />
                <polygon points="120,64 168.5,92 168.5,148 120,176 71.5,148 71.5,92" class="radar-grid inner" />
                <line v-for="(_, idx) in abilityRadar" :key="idx" x1="120" y1="120" :x2="radarAxisPoint(idx).x" :y2="radarAxisPoint(idx).y" class="radar-axis" />
                <polygon :points="radarOldPoints" class="radar-area-old" />
                <polygon :points="radarPoints" class="radar-area" />
                <circle v-for="(item, idx) in abilityRadar" :key="item.name" :cx="radarPoint(idx, item.score).split(',')[0]" :cy="radarPoint(idx, item.score).split(',')[1]" r="3.5" class="radar-dot" />
                <text
                  v-for="(item, idx) in abilityRadar"
                  :key="`percent-${item.name}`"
                  :x="radarPoint(idx, item.score, 96).split(',')[0]"
                  :y="radarPoint(idx, item.score, 96).split(',')[1]"
                  class="radar-percent-label"
                  text-anchor="middle"
                >
                  {{ Math.round(item.score) }}%
                </text>
                <text
                  v-for="(item, idx) in abilityRadar"
                  :key="`label-${item.name}`"
                  :x="radarLabelPoint(idx).x"
                  :y="radarLabelPoint(idx).y"
                  class="radar-label"
                  text-anchor="middle"
                >
                  {{ item.name.replace('能力', '') }}
                </text>
              </svg>
              <div class="radar-legend">
                <span><i class="old"></i>旧</span>
                <span><i></i>新</span>
              </div>
              <div class="ability-list">
                <p v-for="item in abilityRadar" :key="item.name">
                  <span>{{ item.name }}</span>
                  <strong>{{ Math.round(item.old_score ?? 50) }}% → {{ Math.round(item.score) }}%</strong>
                </p>
              </div>
            </section>

            <section class="wrongbook-folders">
              <div v-if="wrongBookError" class="text-sm font-bold text-orange-600">{{ wrongBookError }}</div>
              <div v-if="!wrongBook?.groups?.length" class="studio-empty">暂无错题。完成练习训练后，错题会按专业和课程自动归档。</div>
              <div v-for="major in wrongBook?.groups || []" :key="major.major" class="wrongbook-major">
                <div class="wrongbook-folder-head">
                  <strong>{{ major.major }}</strong>
                  <span>{{ major.count }} 道错题</span>
                </div>
                <div
                  v-for="course in major.courses"
                  v-show="openCourseFolders[folderKey(major.major, course.course)]"
                  :key="course.course"
                  class="wrongbook-course"
                >
                  <div class="wrongbook-course-head">
                    <strong>{{ course.course }}</strong>
                    <span>{{ course.count }} 题</span>
                    <button class="studio-btn ghost" @click="toggleSelectCourseWrongRecords(course)">选择本课程</button>
                    <button class="studio-btn ghost" @click="openRedoCourse(major, course)">重做本课程</button>
                  </div>
                  <article v-for="item in course.items" :key="item.id" class="wrongbook-item">
                    <label class="wrongbook-check">
                      <input
                        type="checkbox"
                        :checked="selectedWrongRecordIds.includes(String(item.id))"
                        @change="onWrongRecordSelection(item, $event)"
                      />
                    </label>
                    <div class="wrongbook-item-main">
                      <div class="tag-row">
                        <span>{{ item.type }}</span>
                        <span v-for="tag in item.tags || []" :key="tag">{{ tag }}</span>
                      </div>
                      <strong>{{ item.stem }}</strong>
                      <p>你的答案：{{ item.answer || '未记录' }}；正确答案：{{ item.correct_answer || '待核验' }}</p>
                      <p v-if="item.analysis">{{ item.analysis }}</p>
                    </div>
                    <div class="wrongbook-item-actions">
                      <button class="studio-btn secondary" @click="openRedo(item)">重做</button>
                      <button class="studio-btn danger" @click="deleteWrongRecord(item)">删除</button>
                    </div>
                  </article>
                </div>
              </div>
            </section>
          </div>
          </template>
          <section v-else class="wrongbook-empty-state" aria-label="错题本为空">
            <div class="wrongbook-empty-state__intro">
              <span class="wrongbook-empty-state__mark">✓</span>
              <div>
                <span>当前无待复盘错题</span>
                <strong>完成一轮定制练习后，错题和能力变化会自动沉淀到这里</strong>
                <p>能力雷达只基于真实作答结果更新，空错题本不会填充模拟分数。</p>
              </div>
            </div>
            <div class="wrongbook-empty-flow">
              <section class="wrongbook-empty-zone">
                <header><span>当前诊断配置</span><strong>本轮练习将使用的真实输入</strong></header>
                <dl>
                  <div><dt>专业方向</dt><dd>{{ effectiveMajor }}</dd></div>
                  <div><dt>当前课程</dt><dd>{{ effectiveCourse }}</dd></div>
                  <div><dt>诊断焦点</dt><dd>{{ specificKnowledgePoint || '待设置知识点' }}</dd></div>
                  <div><dt>题库规格</dt><dd>{{ totalQuestionCount }} 题 · {{ questionDifficultyLabel }}</dd></div>
                  <div><dt>已绑定题库</dt><dd>{{ activeQuestionBankIds.length }} 份</dd></div>
                </dl>
              </section>
              <section class="wrongbook-empty-zone">
                <header><span>真实复盘机制</span><strong>错题从作答到能力变化的处理路径</strong></header>
                <ol>
                  <li><b>1</b><span><strong>提交真实答案</strong><small>训练模式即时判题，考试模式交卷后统一判题</small></span></li>
                  <li><b>2</b><span><strong>保留错因证据</strong><small>记录用户答案、正确答案、解析和知识点标签</small></span></li>
                  <li><b>3</b><span><strong>归档到课程文件夹</strong><small>按专业和课程归类，支持单题、课程和全部重做</small></span></li>
                  <li><b>4</b><span><strong>重做结果继续沉淀</strong><small>答对后移出待复盘区，同步到历史星系</small></span></li>
                </ol>
              </section>
              <section class="wrongbook-empty-evidence">
                <header><span>完成练习后这里会出现的真实证据</span><strong>页面不会在作答前生成虚假分数</strong></header>
                <div>
                  <article><b>错题文件夹</b><span>按专业、课程和知识点组织待复盘题目。</span></article>
                  <article><b>能力雷达</b><span>根据实际正误与重做结果更新六维能力。</span></article>
                  <article><b>历史星系</b><span>重做正确的题目转为已掌握历史证据。</span></article>
                </div>
              </section>
              <section class="wrongbook-empty-rules">
                <header><span>开始前准备</span><strong>当前最短可执行路径</strong></header>
                <ol>
                  <li><b>01</b><span><strong>确认知识点</strong><small>{{ specificKnowledgePoint || '在出题定制页设置具体诊断范围' }}</small></span></li>
                  <li><b>02</b><span><strong>生成独立题库</strong><small>练习诊断不会读取资源工坊的资源组合</small></span></li>
                  <li><b>03</b><span><strong>完成智能做题</strong><small>作答后回到本页查看错题、雷达和历史变化</small></span></li>
                </ol>
              </section>
            </div>
            <div class="studio-actions wrongbook-empty-state__actions">
              <button class="studio-btn secondary" type="button" @click="trySwitchPage('builder')">设置定制题库</button>
              <button class="studio-btn" type="button" @click="trySwitchPage('diagnosis')">进入智能做题</button>
              <button v-if="masteredGalaxyStars.length" class="studio-btn ghost" type="button" @click="openTagGalaxy()">查看 {{ masteredGalaxyStars.length }} 颗历史星</button>
            </div>
          </section>
        </div>
      </section>

      <section v-show="activePage === 'tagGalaxy'" class="studio-panel tag-galaxy-panel">
        <div class="studio-panel-header">
          <div>
            <div class="studio-title"><span class="studio-title-dot green"></span>错题标签星系</div>
            <p>标签按专业、课程和知识点聚合成星系节点，连线表示错题标签之间的关联强度。</p>
          </div>
          <div class="studio-actions">
            <button class="studio-btn ghost" type="button" @click="trySwitchPage('wrongBook')">返回错题本</button>
            <button class="studio-btn secondary" type="button" :disabled="galaxyRefreshing || wrongBookLoading" @click="refreshTagGalaxy">{{ galaxyRefreshing ? '刷新中' : (galaxyRefreshFeedback || '刷新星系') }}</button>
            <div class="galaxy-zoom-tools" role="group" aria-label="错题标签星系缩放控制">
              <button class="studio-btn ghost" type="button" aria-label="缩小错题标签星系" title="缩小 (-)" :disabled="galaxyZoom <= GALAXY_ZOOM_MIN" @click="setGalaxyZoom(galaxyZoom - GALAXY_ZOOM_STEP)">−</button>
              <output aria-live="polite">{{ Math.round(galaxyZoom * 100) }}%</output>
              <button class="studio-btn ghost" type="button" aria-label="放大错题标签星系" title="放大 (+)" :disabled="galaxyZoom >= GALAXY_ZOOM_MAX" @click="setGalaxyZoom(galaxyZoom + GALAXY_ZOOM_STEP)">＋</button>
              <button class="studio-btn ghost" type="button" aria-label="恢复错题标签星系百分之百" title="恢复 100% (0)" :aria-pressed="galaxyZoom === 1" @click="resetGalaxyZoom">100%</button>
            </div>
          </div>
        </div>
        <div class="tag-galaxy-body">
          <div class="tag-galaxy-stage">
            <canvas
              ref="galaxyCanvas"
              aria-label="错题标签星系"
              role="img"
              tabindex="0"
              aria-describedby="tag-galaxy-help"
              @click="onGalaxyClick"
              @mousemove="onGalaxyPointerMove"
              @mouseleave="onGalaxyPointerLeave"
              @wheel.prevent="onGalaxyWheel"
              @keydown="handleGalaxyKeydown"
            ></canvas>
          </div>
          <aside class="tag-galaxy-inspector">
            <div>
              <span>当前标签</span>
              <strong>{{ activeGalaxyNode?.tag || '暂无标签' }}</strong>
            </div>
            <p v-if="activeGalaxyNode">{{ activeGalaxyNode.major }} / {{ activeGalaxyNode.course }}</p>
            <p v-if="activeGalaxyNode">涉及 {{ activeGalaxyNode.count }} 道错题，知识点：{{ activeGalaxyNode.points?.slice(0, 3).join('、') || '综合知识点' }}</p>
            <p id="tag-galaxy-help">移动鼠标会改变星系大小、倾斜和视差；滚轮或 +/- 缩放，按 0 恢复 100%，按 Escape 清除标签。当前缩放：{{ Math.round(galaxyZoom * 100) }}%。</p>
            <span class="galaxy-sr-only" aria-live="polite">{{ galaxyInteractionStatus }}</span>
            <div class="tag-galaxy-clusters">
              <button
                v-for="node in tagGalaxy.nodes"
                :key="node.tag"
                type="button"
                :class="{ active: activeGalaxyTag === node.tag }"
                @click="activeGalaxyTag = node.tag"
              >
                <span>{{ node.tag }}</span>
              </button>
            </div>
          </aside>
        </div>
      </section>

      <section v-show="activePage === 'diagnosis'">
        <div class="studio-panel mb-4 diagnosis-hero-panel">
        <div class="studio-panel-header">
          <div>
            <div class="studio-title"><span class="studio-title-dot green"></span>{{ pathStageTitle }} · 智能做题</div>
            <p>本轮题目全部来自当前路径节点；每次提交都会回写阶段掌握度，完成全部题目后自动判定是否解锁下一阶段。</p>
          </div>
        </div>
        <div class="studio-panel-body">
          <div class="diagnosis-overview-strip">
            <article>
              <span>题库来源</span>
              <strong>{{ questionBankResources.length ? `${questionBankResources.length} 份个性化题库` : '尚未生成题库' }}</strong>
            </article>
            <article>
              <span>本轮题量</span>
              <strong>{{ activeExerciseQuestionLimit }} 题</strong>
            </article>
            <article>
              <span>诊断去向</span>
              <strong>掌握度 · 自动晋级 · 错题本</strong>
            </article>
          </div>
          <div class="tag-row">
            <span>需求定制</span>
            <span>资源生成</span>
            <span>题库出题</span>
            <span>训练诊断</span>
            <span>画像迭代</span>
          </div>
          <p class="studio-muted mt-3">{{ closedLoopStatus }}</p>
        </div>
      </div>
      <ExercisePage
        ref="exercisePageRef"
        :active="activePage === 'diagnosis'"
        :question-bank-ids="activeQuestionBankIds"
        :question-limit="activeExerciseQuestionLimit"
        :difficulty="activeExerciseDifficulty"
        :course-name="pathCourseTitle"
        :knowledge-point="pathStageTitle"
        :question-type-count="selectedQuestionTypes.length"
        :reset-seed="exerciseResetSeed"
        @answered="onExerciseAnswered"
        @navigate="trySwitchPage($event)"
      />
      </section>
    </main>

    <div v-if="showExamLeaveDialog" class="workshop-modal-backdrop">
      <section class="workshop-modal studio-panel">
        <div class="studio-title"><span class="studio-title-dot green"></span>考试正在进行</div>
        <p>切换到其它页面前需要先交卷。交卷后会保留本次作答记录，并生成训练诊断和错题沉淀。</p>
        <div class="studio-actions">
          <button class="studio-btn ghost" @click="cancelSubmitExamAndLeave">继续考试</button>
          <button class="studio-btn" @click="confirmSubmitExamAndLeave">交卷并离开</button>
        </div>
      </section>
    </div>
  </div>
</template>
