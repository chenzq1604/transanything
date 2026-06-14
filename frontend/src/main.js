import { createApp } from 'vue'
import Antd from 'ant-design-vue'
import App from './App.vue'
import 'ant-design-vue/dist/reset.css'
import 'highlight.js/styles/github-dark.css'
import './style.css'

/**
 * 应用入口
 * 创建Vue实例并注册Ant Design Vue
 */
const app = createApp(App)
app.use(Antd)
app.mount('#app')
