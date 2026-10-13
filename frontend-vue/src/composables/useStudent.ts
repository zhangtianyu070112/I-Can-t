import { computed, ref, watch } from 'vue'
import { readStorage, writeStorage } from '@/utils/storage'

const key = 'las_student_id'
const majorKey = 'las_major'
const goalsKey = 'las_goals'

function createLearnerId() {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `learner-${suffix}`
}

const storedStudentId = readStorage('local', key)
const initialStudentId = storedStudentId || createLearnerId()
writeStorage('local', key, initialStudentId)

const studentId = ref(initialStudentId)
const major = ref(readStorage('local', majorKey) || '')
const goals = ref(readStorage('local', goalsKey) || '')

watch(studentId, (v) => writeStorage('local', key, v))
watch(major, (v) => writeStorage('local', majorKey, v))
watch(goals, (v) => writeStorage('local', goalsKey, v))

export function useStudent() {
  return {
    studentId,
    major,
    goals,
    createFreshLearner: () => { studentId.value = createLearnerId() },
    ready: computed(() => Boolean(studentId.value.trim())),
  }
}

