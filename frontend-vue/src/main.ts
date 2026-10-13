import { createApp } from 'vue'
import './style.css'
import './exercise.css'
import './density.css'
import './multimodal.css'
import './studio.css'
import './interface-refresh.css'
import './knowledge-graph.css'
import './profile-center.css'
import './presentation-tight.css'
import './workspace-polish.css'
import './home-landing.css'
import './evaluate-evolution.css'
import './markdown.css'
import './learning-os.css'
import './competition-ui.css'
import './workspace-v2.css'
import './reference-screens.css'
import './final-acceptance.css'
import App from './App.vue'
import router from './router'

// 创建Vue应用实例
const app = createApp(App)

// 使用路由
app.use(router)

// 挂载应用
app.mount('#app')
