import { defineStore } from 'pinia'
import {
  fetchShotDetection,
  rerunShotDetection as requestShotDetectionRerun,
  startShotDetection,
} from '../api/shot-detection'
import type { ShotDetection } from '../types/shot-detection'

interface ShotDetectionState {
  currentDetection: ShotDetection | null
  loading: boolean
  processing: boolean
  errorMessage: string
}

export const useShotDetectionStore = defineStore('shot-detection', {
  state: (): ShotDetectionState => ({
    currentDetection: null,
    loading: false,
    processing: false,
    errorMessage: '',
  }),

  actions: {
    /** 页面加载/刷新时读取当前项目已经存在的 F04 自动检测结果。 */
    async loadShotDetection(projectId: string): Promise<ShotDetection | null> {
      this.loading = true
      this.errorMessage = ''
      try {
        this.currentDetection = await fetchShotDetection(projectId)
        return this.currentDetection
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '自动拉片结果加载失败'
        throw error
      } finally {
        this.loading = false
      }
    },

    /**
     * 用户点击“开始自动拉片”后的唯一前端动作。
     * 真正的 Proxy 校验、TransNetV2、真实 PTS 对齐与 DB ready 全部由后端完成。
     */
    async runShotDetection(projectId: string): Promise<ShotDetection> {
      if (this.processing) throw new Error('自动拉片正在运行，请勿重复提交')
      if (this.currentDetection?.status === 'ready') throw new Error('当前项目已经完成自动拉片')

      this.processing = true
      this.errorMessage = ''
      try {
        const result = await startShotDetection(projectId)
        this.currentDetection = result
        return result
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '自动拉片失败'
        throw error
      } finally {
        this.processing = false
      }
    },

    /**
     * 用户在 READY 页面明确点击“重新自动拉片”后的动作。
     * 前端继续显示旧结果，直到后端新结果完整成功；重跑失败时旧 Auto Evidence 不会被清空。
     */
    async rerunShotDetection(projectId: string): Promise<ShotDetection> {
      if (this.processing) throw new Error('自动拉片正在运行，请勿重复提交')
      if (this.currentDetection?.status !== 'ready') throw new Error('当前项目没有可重新运行的自动拉片结果')

      this.processing = true
      this.errorMessage = ''
      try {
        const result = await requestShotDetectionRerun(projectId)
        this.currentDetection = result
        return result
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '重新自动拉片失败，旧结果已保留'
        throw error
      } finally {
        this.processing = false
      }
    },

    /** 切换项目时清空只属于当前项目的 F04 页面状态。 */
    resetShotDetectionState(): void {
      this.currentDetection = null
      this.loading = false
      this.processing = false
      this.errorMessage = ''
    },
  },
})
