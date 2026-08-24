import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import './styles.css'
import './typography.css'
import './source-video.css'
import './preprocess.css'
import './shot-detection.css'

createApp(App).use(createPinia()).use(router).mount('#app')
