import { createRouter, createWebHistory } from 'vue-router'
import ProjectBreakdownV2 from '../views/ProjectBreakdownV2.vue'
import ProjectListV5 from '../views/ProjectListV5.vue'
import ProjectOutputV1 from '../views/ProjectOutputV1.vue'
import ProjectRemakeV1 from '../views/ProjectRemakeV1.vue'
import ProjectSourceConfirmV1 from '../views/ProjectSourceConfirmV1.vue'
import ProjectSourceVideosV5 from '../views/ProjectSourceVideosV5.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'projects', component: ProjectListV5 },
    { path: '/projects/:projectId', name: 'studio', component: ProjectSourceVideosV5 },
    { path: '/projects/:projectId/breakdown', name: 'breakdown', component: ProjectBreakdownV2 },
    { path: '/projects/:projectId/source-confirm', name: 'source-confirm', component: ProjectSourceConfirmV1 },
    { path: '/projects/:projectId/remake', name: 'remake', component: ProjectRemakeV1 },
    { path: '/projects/:projectId/output', name: 'output', component: ProjectOutputV1 },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
