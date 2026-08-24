import { createRouter, createWebHistory } from 'vue-router'
import ProjectList from '../views/ProjectList.vue'
import ProjectStudio from '../views/ProjectStudio.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'projects', component: ProjectList },
    { path: '/projects/:projectId', name: 'studio', component: ProjectStudio },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
