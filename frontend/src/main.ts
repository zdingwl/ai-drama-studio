import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './styles.css'
import './f05.css'
import './shot-manager.css'
import './shot-revision.css'
import './shot-workbench-v3.css'
import './shot-workbench-v3-overrides.css'
import './task-progress.css'

createApp(App).use(router).mount('#app')
