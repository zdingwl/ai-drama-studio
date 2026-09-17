import { createRouter, createWebHistory } from 'vue-router'

import ProjectListView from '@/views/ProjectListView.vue'
import ProjectWorkspaceView from '@/views/ProjectWorkspaceView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'projects',
      component: ProjectListView,
    },
    {
      path: '/projects/:id',
      redirect: (to) => ({
        path: `/projects/${String(to.params.id)}/overview`,
      }),
    },
    {
      path: '/projects/:id/:workspace(overview|episodes|source|localize|assets|prompts|generation|script|storyboard|final)',
      name: 'project-workspace',
      component: ProjectWorkspaceView,
    },
  ],
})

export default router
