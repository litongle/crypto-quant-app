import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import './styles/index.scss'

// 导入自定义指令
import directives from './directives'

// 导入全局组件
import SvgIcon from './components/SvgIcon/index.vue'
import DataCard from './components/DataCard/index.vue'
import TrendChart from './components/TrendChart/index.vue'
import StatusTag from './components/StatusTag/index.vue'

// 导入全局工具
import { formatDateTime, formatNumber } from './utils/formatter'

// 创建Vue应用
const app = createApp(App)

// 配置Pinia状态管理
const pinia = createPinia()
app.use(pinia)

// 配置路由
app.use(router)

// 配置Element Plus
app.use(ElementPlus, {
  locale: zhCn,
  size: 'default',
  zIndex: 3000,
})

// 注册Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 注册全局组件
app.component('SvgIcon', SvgIcon)
app.component('DataCard', DataCard)
app.component('TrendChart', TrendChart)
app.component('StatusTag', StatusTag)

// 注册自定义指令
Object.keys(directives).forEach(key => {
  app.directive(key, directives[key])
})

// 注册全局属性
app.config.globalProperties.$filters = {
  formatDateTime,
  formatNumber
}

// 错误处理
app.config.errorHandler = (err, vm, info) => {
  console.error('Vue全局错误:', err, info)
  // 可以在这里添加错误上报逻辑
}

// 性能追踪
if (import.meta.env.DEV) {
  app.config.performance = true
}

// 挂载应用
app.mount('#app')

// 导出app实例，便于在其他地方使用
export default app
