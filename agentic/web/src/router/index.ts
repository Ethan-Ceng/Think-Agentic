import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/sessions',
      redirect: '/',
    },
    {
      path: '/sessions/:id',
      name: 'session',
      component: () => import('@/views/SessionView.vue'),
    },
  ],
})

export default router
