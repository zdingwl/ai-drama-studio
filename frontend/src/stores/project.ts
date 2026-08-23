import { defineStore } from 'pinia'
import { createProject, fetchProjects, openProjectRequest } from '../api/projects'
import type { CreateProjectPayload, Project } from '../types/project'

interface ProjectState {
  projects: Project[]
  currentProject: Project | null
  loading: boolean
  creating: boolean
  opening: boolean
  errorMessage: string
}

export const useProjectStore = defineStore('project', {
  state: (): ProjectState => ({
    projects: [],
    currentProject: null,
    loading: false,
    creating: false,
    opening: false,
    errorMessage: '',
  }),
  actions: {
    /** 首页加载项目列表；只调用 GET /api/projects，不打开任何项目。 */
    async loadProjects(): Promise<void> {
      this.loading = true
      this.errorMessage = ''
      try {
        this.projects = await fetchProjects()
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '项目列表加载失败'
      } finally {
        this.loading = false
      }
    },

    /**
     * 用户点击“创建项目”后的前端核心动作。
     * 防止重复提交；成功后保存 currentProject，页面跳转由组件负责。
     */
    async submitCreateProject(payload: CreateProjectPayload): Promise<Project> {
      if (this.creating) {
        throw new Error('项目正在创建，请勿重复提交')
      }
      this.creating = true
      this.errorMessage = ''
      try {
        const project = await createProject(payload)
        this.currentProject = project
        this.projects = [project, ...this.projects.filter((item) => item.id !== project.id)]
        return project
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '项目创建失败'
        throw error
      } finally {
        this.creating = false
      }
    },

    /**
     * 点击历史项目、刷新 Workspace 或直接访问项目 URL 时统一调用。
     * 后端验证通过后才写入 currentProject。
     */
    async openProject(projectId: string): Promise<Project> {
      this.opening = true
      this.errorMessage = ''
      try {
        const project = await openProjectRequest(projectId)
        this.currentProject = project
        const index = this.projects.findIndex((item) => item.id === project.id)
        if (index >= 0) this.projects[index] = project
        return project
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '项目打开失败'
        throw error
      } finally {
        this.opening = false
      }
    },
  },
})
