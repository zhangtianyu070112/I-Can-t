import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const HomePage = () => import('@/pages/HomePage.vue')
const ProfilePage = () => import('@/pages/ProfilePage.vue')
const WorkshopPage = () => import('@/pages/WorkshopPage.vue')
const KnowledgePage = () => import('@/pages/KnowledgePage.vue')
const MultimodalPage = () => import('@/pages/MultimodalPage.vue')
const ExercisePage = () => import('@/pages/ExerciseCenterPage.vue')
const PathPage = () => import('@/pages/PathPage.vue')
const TutorPage = () => import('@/pages/TutorPage.vue')
const EvaluatePage = () => import('@/pages/EvaluatePage.vue')

// 定义路由配置
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: HomePage,
  },
  {
    path: '/profile',
    name: 'profile',
    component: ProfilePage,
  },
  {
    path: '/workshop',
    name: 'workshop',
    component: WorkshopPage,
  },
  {
    path: '/knowledge',
    name: 'knowledge',
    component: KnowledgePage,
  },
  {
    path: '/multimodal',
    name: 'multimodal',
    component: MultimodalPage,
  },
  {
    path: '/exercise',
    name: 'exercise',
    component: ExercisePage,
  },
  {
    path: '/path',
    name: 'path',
    component: PathPage,
  },
  {
    path: '/tutor',
    name: 'tutor',
    component: TutorPage,
  },
  {
    path: '/evaluate',
    name: 'evaluate',
    component: EvaluatePage,
  },
  {
    path: '/settings',
    redirect: '/',
  },
]

// 创建路由实例
const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
