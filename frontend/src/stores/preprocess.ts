import { defineStore } from 'pinia'
import { fetchSourcePreprocess, startSourcePreprocess } from '../api/preprocess'
import type { SourcePreprocess } from '../types/preprocess'

interface PreprocessState {
  currentPreprocess: SourcePreprocess | null
  loading: boolean
  processing: boolean
  errorMessage: string
}

export const usePreprocessStore = defineStore('preprocess', {
  state: (): PreprocessState => ({
    currentPreprocess: null,
    loading: false,
    processing: false,
    errorMessage: '',
  }),

  actions: {
    /** 页面加载/刷新时读取当前项目已经完成的预处理结果。 */
    async loadPreprocess(projectId: string): Promise<SourcePreprocess | null> {
      this.loading = true
      this.errorMessage = ''
      try {
        this.currentPreprocess = await fetchSourcePreprocess(projectId)
        return this.currentPreprocess
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '视频预处理信息加载失败'
        throw error
      } finally {
        this.loading = false
      }
    },

    /**
     * 用户点击“开始视频预处理”后的前端总动作。
     * 前端不伪造百分比；后端真正执行 Source Integrity、FFmpeg、校验、发布和 DB ready。
     */
    async runPreprocess(projectId: string): Promise<SourcePreprocess> {
      if (this.processing) throw new Error('视频正在预处理，请勿重复提交')
      if (this.currentPreprocess) throw new Error('当前项目已经完成视频预处理')

      this.processing = true
      this.errorMessage = ''
      try {
        const result = await startSourcePreprocess(projectId)
        this.currentPreprocess = result
        return result
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '视频预处理失败'
        throw error
      } finally {
        this.processing = false
      }
    },

    /** 切换项目时清空只属于当前项目的 F03 页面状态。 */
    resetPreprocessState(): void {
      this.currentPreprocess = null
      this.loading = false
      this.processing = false
      this.errorMessage = ''
    },
  },
})
