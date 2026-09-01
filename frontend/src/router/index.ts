import { createRouter, createWebHistory } from 'vue-router'
import ProjectListV4 from '../views/ProjectListV4.vue'
import ProjectStudioV4 from '../views/ProjectStudioV4.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'projects', component: ProjectListV4 },
    { path: '/projects/:projectId', name: 'studio', component: ProjectStudioV4 },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
