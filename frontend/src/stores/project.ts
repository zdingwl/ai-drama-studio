import { defineStore } from 'pinia'
import { startSourcePreprocess } from '../api/preprocess'
import { createProject, fetchProjects, openProjectRequest } from '../api/projects'
import { uploadSourceVideo } from '../api/source-videos'
import type { CreateProjectPayload, Project } from '../types/project'

export type ProjectImportStage = 'idle' | 'creating' | 'uploading' | 'initializing' | 'ready'

interface ProjectState {
  projects: Project[]
  currentProject: Project | null
  loading: boolean
  creating: boolean
  opening: boolean
  errorMessage: string
  importStage: ProjectImportStage
  importProgress: number
}

export const useProjectStore = defineStore('project', {
  state: (): ProjectState => ({
    projects: [],
    currentProject: null,
    loading: false,
    creating: false,
    opening: false,
    errorMessage: '',
    importStage: 'idle',
    importProgress: 0,
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
     * 兼容底层 F01 的单独创建入口。新的普通用户流程不再调用它；
     * Workflow 01 统一使用 submitCreateAndImport()。
     */
    async submitCreateProject(payload: CreateProjectPayload): Promise<Project> {
      if (this.creating) throw new Error('项目正在创建，请勿重复提交')
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
     * Workflow 01「导入原片」的前端单一动作。
     *
     * 用户只提交一次表单；内部按已冻结能力顺序执行：
     * createProject → uploadSourceVideo → startSourcePreprocess。
     * 页面不再要求用户分别进入“视频导入”和“视频预处理”两个页面点击。
     *
     * 输入：项目基础字段 + 用户选择的原片 File。
     * 输出：已经完成 Project / Source / Proxy / WAV / Thumbnail 初始化的 Project。
     * 为什么存在：把工程 Feature 边界隐藏在一个连续 Workflow 后面。
     */
    async submitCreateAndImport(payload: CreateProjectPayload, file: File): Promise<Project> {
      if (this.creating) throw new Error('原片正在导入并初始化，请勿重复提交')
      this.creating = true
      this.errorMessage = ''
      this.importStage = 'creating'
      this.importProgress = 0

      try {
        const project = await createProject(payload)
        this.currentProject = project
        this.projects = [project, ...this.projects.filter((item) => item.id !== project.id)]

        this.importStage = 'uploading'
        await uploadSourceVideo(project.id, file, (progress) => {
          this.importProgress = progress.percent
        })

        this.importStage = 'initializing'
        this.importProgress = 100
        await startSourcePreprocess(project.id)

        this.importStage = 'ready'
        return project
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '原片导入或初始化失败'
        throw error
      } finally {
        this.creating = false
      }
    },

    /** 重置 Workflow 01 的瞬时 UI 状态；不修改任何已经落盘的项目数据。 */
    resetImportWorkflowState(): void {
      if (this.creating) return
      this.importStage = 'idle'
      this.importProgress = 0
      this.errorMessage = ''
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
