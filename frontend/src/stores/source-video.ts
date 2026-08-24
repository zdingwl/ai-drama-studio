import { defineStore } from 'pinia'
import { fetchSourceVideo, uploadSourceVideo } from '../api/source-videos'
import type { SourceVideo } from '../types/source-video'

interface SourceVideoState {
  currentSourceVideo: SourceVideo | null
  loading: boolean
  uploading: boolean
  processing: boolean
  uploadPercent: number
  uploadedBytes: number
  totalBytes: number
  errorMessage: string
}

export const useSourceVideoStore = defineStore('source-video', {
  state: (): SourceVideoState => ({
    currentSourceVideo: null,
    loading: false,
    uploading: false,
    processing: false,
    uploadPercent: 0,
    uploadedBytes: 0,
    totalBytes: 0,
    errorMessage: '',
  }),

  actions: {
    /** 页面进入或刷新时从后端读取已经完成的 Source Video。 */
    async loadSourceVideo(projectId: string): Promise<SourceVideo | null> {
      this.loading = true
      this.errorMessage = ''
      try {
        this.currentSourceVideo = await fetchSourceVideo(projectId)
        return this.currentSourceVideo
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '原视频信息加载失败'
        throw error
      } finally {
        this.loading = false
      }
    },

    /**
     * 用户点击“开始导入”后的前端总动作。
     * 浏览器只负责上传和显示进度；后端真正完成 staging、Hash、FFprobe、ready。
     */
    async importSourceVideo(projectId: string, file: File): Promise<SourceVideo> {
      if (this.uploading) throw new Error('原视频正在导入，请勿重复提交')
      if (this.currentSourceVideo) throw new Error('当前项目已经存在原视频，不能重复导入')

      this.uploading = true
      this.processing = false
      this.uploadPercent = 0
      this.uploadedBytes = 0
      this.totalBytes = file.size
      this.errorMessage = ''

      try {
        const sourceVideo = await uploadSourceVideo(projectId, file, (progress) => {
          this.uploadPercent = progress.percent
          this.uploadedBytes = progress.loaded
          this.totalBytes = progress.total
          this.processing = progress.percent >= 100
        })
        this.currentSourceVideo = sourceVideo
        this.uploadPercent = 100
        return sourceVideo
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '原视频导入失败'
        throw error
      } finally {
        this.uploading = false
        this.processing = false
      }
    },

    /** 离开项目或切换项目时清空只属于当前页面的 Source 状态。 */
    resetSourceVideoState(): void {
      this.currentSourceVideo = null
      this.loading = false
      this.uploading = false
      this.processing = false
      this.uploadPercent = 0
      this.uploadedBytes = 0
      this.totalBytes = 0
      this.errorMessage = ''
    },
  },
})
