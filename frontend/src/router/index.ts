import { createRouter, createWebHistory } from 'vue-router'
import ProjectBreakdownV1 from '../views/ProjectBreakdownV1.vue'
import ProjectListV5 from '../views/ProjectListV5.vue'
import ProjectSourceVideosV5 from '../views/ProjectSourceVideosV5.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'projects', component: ProjectListV5 },
    { path: '/projects/:projectId', name: 'studio', component: ProjectSourceVideosV5 },
    { path: '/projects/:projectId/breakdown', name: 'breakdown', component: ProjectBreakdownV1 },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
