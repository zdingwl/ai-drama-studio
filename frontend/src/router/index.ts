import { createRouter, createWebHistory } from 'vue-router'
import ProjectList from '../views/ProjectList.vue'
import ProjectStudioV3 from '../views/ProjectStudioV3.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'projects', component: ProjectList },
    { path: '/projects/:projectId', name: 'studio', component: ProjectStudioV3 },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})