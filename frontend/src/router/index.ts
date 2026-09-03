import { createRouter, createWebHistory } from 'vue-router'
import ProjectListV5 from '../views/ProjectListV5.vue'
import ProjectStudioV4 from '../views/ProjectStudioV4.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'projects', component: ProjectListV5 },
    { path: '/projects/:projectId', name: 'studio', component: ProjectStudioV4 },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
