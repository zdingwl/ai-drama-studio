import { createRouter, createWebHistory } from 'vue-router'
import ProjectHome from '../views/ProjectHome.vue'
import ProjectWorkspace from '../views/ProjectWorkspace.vue'
import SourceVideoImport from '../views/SourceVideoImport.vue'
import VideoPreprocess from '../views/VideoPreprocess.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'projects', component: ProjectHome },
    { path: '/projects/:projectId', name: 'workspace', component: ProjectWorkspace },
    {
      path: '/projects/:projectId/source-video',
      name: 'source-video',
      component: SourceVideoImport,
    },
    {
      path: '/projects/:projectId/preprocess',
      name: 'preprocess',
      component: VideoPreprocess,
    },
  ],
})
