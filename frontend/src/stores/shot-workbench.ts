import { defineStore } from 'pinia'
import {
  confirmShotWorkbench,
  fetchShotWorkbench,
  initializeShotWorkbench,
  mergeShots,
  splitShot,
  updateShotBoundary,
} from '../api/shot-workbench'
import type { ShotWorkbench } from '../types/shot-workbench'

interface ShotWorkbenchState {
  currentWorkbench: ShotWorkbench | null
  loading: boolean
  saving: boolean
  errorMessage: string
}

export const useShotWorkbenchStore = defineStore('shot-workbench', {
  state: (): ShotWorkbenchState => ({
    currentWorkbench: null,
    loading: false,
    saving: false,
    errorMessage: '',
  }),

  actions: {
    /** 进入 F05 时读取已有 Final Shot；第一次进入会从 F04 自动初始化。 */
    async loadOrInitialize(projectId: string): Promise<ShotWorkbench> {
      this.loading = true
      this.errorMessage = ''
      try {
        let result = await fetchShotWorkbench(projectId)
        if (!result) result = await initializeShotWorkbench(projectId)
        this.currentWorkbench = result
        return result
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '镜头工作台加载失败'
        throw error
      } finally {
        this.loading = false
      }
    },

    async adjustBoundary(projectId: string, leftShotId: string, boundaryUs: number): Promise<ShotWorkbench> {
      return this._save(() => updateShotBoundary(projectId, leftShotId, boundaryUs))
    },

    async split(projectId: string, shotId: string, splitUs: number): Promise<ShotWorkbench> {
      return this._save(() => splitShot(projectId, shotId, splitUs))
    },

    async merge(projectId: string, leftShotId: string): Promise<ShotWorkbench> {
      return this._save(() => mergeShots(projectId, leftShotId))
    },

    async confirm(projectId: string): Promise<ShotWorkbench> {
      return this._save(() => confirmShotWorkbench(projectId))
    },

    /** 所有写操作统一维护 saving/error/currentWorkbench，避免每个按钮复制状态逻辑。 */
    async _save(operation: () => Promise<ShotWorkbench>): Promise<ShotWorkbench> {
      if (this.saving) throw new Error('镜头修改正在保存，请稍候')
      this.saving = true
      this.errorMessage = ''
      try {
        const result = await operation()
        this.currentWorkbench = result
        return result
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '镜头修改保存失败'
        throw error
      } finally {
        this.saving = false
      }
    },

    reset(): void {
      this.currentWorkbench = null
      this.loading = false
      this.saving = false
      this.errorMessage = ''
    },
  },
})
