import { defineStore } from 'pinia'
import {
  fetchCharacterDetection,
  rerunCharacterDetection as requestCharacterDetectionRerun,
  startCharacterDetection,
} from '../api/character-detection'
import type { CharacterDetection } from '../types/character-detection'

interface CharacterDetectionState {
  currentDetection: CharacterDetection | null
  loading: boolean
  processing: boolean
  errorMessage: string
}

export const useCharacterDetectionStore = defineStore('character-detection', {
  state: (): CharacterDetectionState => ({
    currentDetection: null,
    loading: false,
    processing: false,
    errorMessage: '',
  }),

  actions: {
    async loadCharacterDetection(projectId: string): Promise<CharacterDetection | null> {
      this.loading = true
      this.errorMessage = ''
      try {
        this.currentDetection = await fetchCharacterDetection(projectId)
        return this.currentDetection
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '人物识别结果加载失败'
        throw error
      } finally {
        this.loading = false
      }
    },

    async runCharacterDetection(projectId: string): Promise<CharacterDetection> {
      if (this.processing) throw new Error('人物识别正在运行，请勿重复提交')
      if (this.currentDetection?.status === 'ready') throw new Error('当前项目已经完成人物识别')
      this.processing = true
      this.errorMessage = ''
      try {
        const result = await startCharacterDetection(projectId)
        this.currentDetection = result
        return result
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '自动人物识别失败'
        throw error
      } finally {
        this.processing = false
      }
    },

    async rerunCharacterDetection(projectId: string): Promise<CharacterDetection> {
      if (this.processing) throw new Error('人物识别正在运行，请勿重复提交')
      if (this.currentDetection?.status !== 'ready') throw new Error('当前没有可重新运行的人物识别结果')
      this.processing = true
      this.errorMessage = ''
      try {
        const result = await requestCharacterDetectionRerun(projectId)
        this.currentDetection = result
        return result
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '重新人物识别失败，旧结果已保留'
        throw error
      } finally {
        this.processing = false
      }
    },

    resetCharacterDetectionState(): void {
      this.currentDetection = null
      this.loading = false
      this.processing = false
      this.errorMessage = ''
    },
  },
})
