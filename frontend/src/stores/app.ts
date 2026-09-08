import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    ready: false,
  }),
  actions: {
    markReady() {
      this.ready = true
    },
  },
})
