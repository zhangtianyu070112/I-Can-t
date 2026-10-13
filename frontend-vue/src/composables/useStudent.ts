import { computed, ref, watch } from 'vue'

const key = 'las_student_id'
const majorKey = 'las_major'
const goalsKey = 'las_goals'

function createLearnerId() {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `learner-${suffix}`
}

const storedStudentId = localStorage.getItem(key)
const initialStudentId = storedStudentId || createLearnerId()
localStorage.setItem(key, initialStudentId)

const studentId = ref(initialStudentId)
const major = ref(localStorage.getItem(majorKey) || '')
const goals = ref(localStorage.getItem(goalsKey) || '')

watch(studentId, (v) => localStorage.setItem(key, v))
watch(major, (v) => localStorage.setItem(majorKey, v))
watch(goals, (v) => localStorage.setItem(goalsKey, v))

export function useStudent() {
  return {
    studentId,
    major,
    goals,
    createFreshLearner: () => { studentId.value = createLearnerId() },
    ready: computed(() => Boolean(studentId.value.trim())),
  }
}

