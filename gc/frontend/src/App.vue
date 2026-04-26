<template>
  <el-config-provider :locale="zhCn" :size="size" :z-index="3000" :button="buttonConfig">
    <div class="app-wrapper" :class="{ 'dark-mode': isDarkMode }">
      <router-view v-slot="{ Component }">
        <transition name="fade-transform" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </div>
  </el-config-provider>
</template>

<script setup lang="ts">
import { ref, provide, onMounted, watch } from 'vue'
import { ElConfigProvider, ElMessage } from 'element-plus'
import zhCn from 'element-plus/lib/locale/lang/zh-cn'
import { useAppStore } from '@/store/modules/app'
import { useUserStore } from '@/store/modules/user'
import { usePermissionStore } from '@/store/modules/permission'

// 组件大小
const size = ref('default')

// 按钮配置
const buttonConfig = ref({
  autoInsertSpace: true
})

// 主题模式
const isDarkMode = ref(false)

// 获取存储
const appStore = useAppStore()
const userStore = useUserStore()
const permissionStore = usePermissionStore()

// 提供主题切换函数给子组件
const toggleDarkMode = () => {
  isDarkMode.value = !isDarkMode.value
  appStore.setDarkMode(isDarkMode.value)
  
  // 更新文档根元素类名
  if (isDarkMode.value) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
  
  // 保存到本地存储
  localStorage.setItem('darkMode', isDarkMode.value ? '1' : '0')
}

// 提供给子组件使用
provide('toggleDarkMode', toggleDarkMode)
provide('isDarkMode', isDarkMode)

// 监听主题变化
watch(
  () => appStore.darkMode,
  (val) => {
    isDarkMode.value = val
  }
)

// 初始化应用
const initApp = async () => {
  try {
    // 从本地存储或系统偏好设置中获取主题模式
    const savedDarkMode = localStorage.getItem('darkMode')
    if (savedDarkMode !== null) {
      isDarkMode.value = savedDarkMode === '1'
    } else {
      // 检查系统偏好
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      isDarkMode.value = prefersDark
    }
    
    appStore.setDarkMode(isDarkMode.value)
    
    // 更新文档根元素类名
    if (isDarkMode.value) {
      document.documentElement.classList.add('dark')
    }
    
    // 获取用户信息和权限
    if (userStore.token) {
      await userStore.getUserInfo()
      // 生成路由
      await permissionStore.generateRoutes()
    }
  } catch (error) {
    console.error('初始化应用失败:', error)
    ElMessage.error('系统初始化失败，请刷新页面重试')
  }
}

onMounted(() => {
  initApp()
})
</script>

<style lang="scss">
// 导入全局样式
@import '@/styles/variables.scss';
@import '@/styles/reset.scss';
@import '@/styles/transitions.scss';

// 根应用样式
.app-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 100vh;
  background-color: var(--bg-color);
  color: var(--text-color);
  transition: background-color 0.3s, color 0.3s;
  
  // 暗色模式
  &.dark-mode {
    --bg-color: #121212;
    --bg-color-secondary: #1e1e1e;
    --text-color: #f0f0f0;
    --text-color-secondary: #aaaaaa;
    --border-color: #333333;
    --hover-color: #2a2a2a;
    --active-color: #0a84ff;
    --success-color: #46c93a;
    --warning-color: #ffb302;
    --danger-color: #ff4a4a;
    --info-color: #909399;
    
    // 覆盖Element Plus的一些样式
    .el-card {
      background-color: var(--bg-color-secondary);
      border-color: var(--border-color);
      color: var(--text-color);
    }
    
    .el-table {
      background-color: var(--bg-color-secondary);
      color: var(--text-color);
      
      th, td {
        background-color: var(--bg-color-secondary);
        border-color: var(--border-color);
      }
    }
    
    .el-input__inner {
      background-color: var(--bg-color-secondary);
      color: var(--text-color);
      border-color: var(--border-color);
    }
  }
}

// 全局CSS变量
:root {
  --bg-color: #f5f7fa;
  --bg-color-secondary: #ffffff;
  --text-color: #2c3e50;
  --text-color-secondary: #606266;
  --border-color: #dcdfe6;
  --hover-color: #f0f2f5;
  --active-color: #409eff;
  --success-color: #67c23a;
  --warning-color: #e6a23c;
  --danger-color: #f56c6c;
  --info-color: #909399;
  
  // 布局相关
  --header-height: 60px;
  --sidebar-width: 220px;
  --sidebar-collapsed-width: 64px;
  --transition-duration: 0.3s;
  
  // 字体相关
  --font-family: 'Noto Sans SC', sans-serif, system-ui, -apple-system, BlinkMacSystemFont;
  --font-size-base: 14px;
  --font-size-small: 13px;
  --font-size-large: 16px;
  --font-weight-normal: 400;
  --font-weight-bold: 600;
  --line-height-base: 1.5;
}

// 全局滚动条样式
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background-color: var(--bg-color);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb {
  background-color: #c0c4cc;
  border-radius: 4px;
  
  &:hover {
    background-color: #909399;
  }
}

// 暗色模式滚动条
.dark-mode {
  ::-webkit-scrollbar-track {
    background-color: var(--bg-color-secondary);
  }
  
  ::-webkit-scrollbar-thumb {
    background-color: #555555;
    
    &:hover {
      background-color: #666666;
    }
  }
}

// 基本样式重置
html, body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  font-family: var(--font-family);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
  color: var(--text-color);
  background-color: var(--bg-color);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

#app {
  width: 100%;
  height: 100%;
}

// 全局链接样式
a {
  color: var(--active-color);
  text-decoration: none;
  
  &:hover {
    text-decoration: underline;
  }
}

// 全局过渡效果
.fade-transform-enter-active,
.fade-transform-leave-active {
  transition: all var(--transition-duration);
}

.fade-transform-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}

.fade-transform-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>
