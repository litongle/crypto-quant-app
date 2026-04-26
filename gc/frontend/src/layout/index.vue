<template>
  <div class="app-wrapper" :class="{ 'mobile': isMobile, 'sidebar-hidden': !sidebarVisible }">
    <!-- Sidebar -->
    <div class="sidebar-container" :class="{ 'collapsed': isCollapsed }">
      <!-- Logo -->
      <div class="logo-container">
        <router-link to="/">
          <img v-if="!isCollapsed" src="@/assets/logo-full.png" alt="RSI Tracker" class="logo-full">
          <img v-else src="@/assets/logo-icon.png" alt="RSI" class="logo-icon">
        </router-link>
      </div>
      
      <!-- Menu -->
      <el-scrollbar>
        <el-menu
          :default-active="activeMenu"
          :collapse="isCollapsed"
          :unique-opened="true"
          :collapse-transition="false"
          :background-color="variables.menuBg"
          :text-color="variables.menuText"
          :active-text-color="variables.menuActiveText"
          mode="vertical"
        >
          <sidebar-item
            v-for="route in permissionStore.routes"
            :key="route.path"
            :item="route"
            :base-path="route.path"
            :is-collapsed="isCollapsed"
          />
        </el-menu>
      </el-scrollbar>
      
      <!-- Collapse button -->
      <div class="sidebar-toggle" @click="toggleSidebar">
        <el-icon :class="{ 'is-active': !isCollapsed }">
          <component :is="isCollapsed ? 'Expand' : 'Fold'" />
        </el-icon>
      </div>
    </div>
    
    <!-- Mobile sidebar mask -->
    <div v-if="isMobile && sidebarVisible" class="sidebar-mask" @click="closeSidebar" />
    
    <!-- Main container -->
    <div class="main-container">
      <!-- Header -->
      <div class="header-container">
        <!-- Left section: Mobile toggle and breadcrumb -->
        <div class="header-left">
          <div v-if="isMobile" class="mobile-toggle" @click="toggleSidebar">
            <el-icon><Menu /></el-icon>
          </div>
          
          <breadcrumb />
        </div>
        
        <!-- Center section: Market ticker -->
        <div class="market-ticker" v-if="!isMobile">
          <market-ticker />
        </div>
        
        <!-- Right section: Actions and user info -->
        <div class="header-right">
          <!-- WebSocket status indicator -->
          <el-tooltip
            :content="wsConnected ? 'WebSocket连接正常' : 'WebSocket连接断开'"
            placement="bottom"
          >
            <div class="ws-status" :class="{ 'connected': wsConnected, 'disconnected': !wsConnected }">
              <el-icon><Connection /></el-icon>
            </div>
          </el-tooltip>
          
          <!-- Theme toggle -->
          <el-tooltip :content="isDark ? '切换到亮色模式' : '切换到暗色模式'" placement="bottom">
            <div class="theme-toggle" @click="toggleTheme">
              <el-icon v-if="isDark"><Sunny /></el-icon>
              <el-icon v-else><Moon /></el-icon>
            </div>
          </el-tooltip>
          
          <!-- Notifications -->
          <el-dropdown trigger="click" @command="handleNotificationCommand">
            <div class="notification-icon">
              <el-badge :value="unreadNotifications" :hidden="unreadNotifications === 0">
                <el-icon><Bell /></el-icon>
              </el-badge>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <div class="dropdown-header">
                  <span>系统通知</span>
                  <el-button v-if="notifications.length > 0" type="text" @click.stop="markAllAsRead">
                    全部已读
                  </el-button>
                </div>
                <el-divider style="margin: 5px 0" />
                <el-empty v-if="notifications.length === 0" description="暂无通知" :image-size="48" />
                <el-dropdown-item v-for="(notification, index) in notifications" :key="index" :command="notification.id">
                  <div class="notification-item" :class="{ 'unread': !notification.read }">
                    <el-icon :class="['notification-icon', notification.type]">
                      <component :is="getNotificationIcon(notification.type)" />
                    </el-icon>
                    <div class="notification-content">
                      <div class="notification-title">{{ notification.title }}</div>
                      <div class="notification-message">{{ notification.message }}</div>
                      <div class="notification-time">{{ formatTime(notification.time) }}</div>
                    </div>
                  </div>
                </el-dropdown-item>
                <el-divider v-if="notifications.length > 0" style="margin: 5px 0" />
                <el-dropdown-item v-if="notifications.length > 0" command="viewAll">
                  <div style="text-align: center; color: var(--el-color-primary);">查看全部通知</div>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          
          <!-- User dropdown -->
          <el-dropdown trigger="click" @command="handleUserCommand">
            <div class="user-info">
              <el-avatar :size="32" :src="userStore.avatar || defaultAvatar" />
              <span class="username" v-if="!isMobile">{{ userStore.name }}</span>
              <el-icon class="dropdown-icon"><CaretBottom /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon>个人中心
                </el-dropdown-item>
                <el-dropdown-item command="password">
                  <el-icon><Lock /></el-icon>修改密码
                </el-dropdown-item>
                <el-divider style="margin: 5px 0" />
                <el-dropdown-item command="logout">
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
      
      <!-- Main content -->
      <div class="main-content">
        <el-scrollbar>
          <app-main />
        </el-scrollbar>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useUserStore } from '@/store/modules/user'
import { usePermissionStore } from '@/store/modules/permission'
import { useAppStore } from '@/store/modules/app'
import { ElMessageBox } from 'element-plus'
import { 
  Menu, Fold, Expand, Bell, User, Lock, SwitchButton, 
  Connection, Sunny, Moon, WarningFilled, SuccessFilled, 
  InfoFilled, CircleCloseFilled, CaretBottom
} from '@element-plus/icons-vue'
import SidebarItem from './components/SidebarItem.vue'
import Breadcrumb from './components/Breadcrumb.vue'
import AppMain from './components/AppMain.vue'
import MarketTicker from './components/MarketTicker.vue'
import defaultAvatar from '@/assets/default-avatar.png'
import { useWebSocket } from '@/composables/useWebSocket'
import { formatDistanceToNow } from 'date-fns'
import { zhCN } from 'date-fns/locale'

// Stores
const userStore = useUserStore()
const permissionStore = usePermissionStore()
const appStore = useAppStore()
const { sidebar, device, theme } = storeToRefs(appStore)

// Router
const route = useRoute()
const router = useRouter()

// Computed
const isCollapsed = computed(() => sidebar.value.opened === false)
const isMobile = computed(() => device.value === 'mobile')
const sidebarVisible = computed(() => isMobile.value ? sidebar.value.opened : true)
const isDark = computed(() => theme.value === 'dark')

// CSS variables
const variables = computed(() => {
  return {
    menuBg: isDark.value ? '#1f2937' : '#ffffff',
    menuText: isDark.value ? '#a0aec0' : '#303133',
    menuActiveText: '#409eff'
  }
})

// Active menu
const activeMenu = computed(() => {
  const { meta, path } = route
  if (meta.activeMenu) {
    return meta.activeMenu as string
  }
  return path
})

// WebSocket connection
const { connected: wsConnected } = useWebSocket()

// Notifications
const notifications = ref<Array<{
  id: string;
  title: string;
  message: string;
  type: 'success' | 'warning' | 'info' | 'error';
  time: Date;
  read: boolean;
}>>([
  {
    id: '1',
    title: '系统通知',
    message: '系统已成功启动，所有服务运行正常',
    type: 'success',
    time: new Date(),
    read: false
  },
  {
    id: '2',
    title: '交易提醒',
    message: 'ETH/USDT 触发RSI超卖信号，已开多单',
    type: 'info',
    time: new Date(Date.now() - 30 * 60 * 1000),
    read: false
  },
  {
    id: '3',
    title: '账户警告',
    message: 'OKX API密钥即将过期，请及时更新',
    type: 'warning',
    time: new Date(Date.now() - 2 * 60 * 60 * 1000),
    read: false
  }
])

const unreadNotifications = computed(() => {
  return notifications.value.filter(n => !n.read).length
})

// Methods
const toggleSidebar = () => {
  appStore.toggleSidebar()
}

const closeSidebar = () => {
  appStore.closeSidebar()
}

const toggleTheme = () => {
  appStore.toggleTheme()
  // Update document class for theme
  if (isDark.value) {
    document.documentElement.classList.add('dark-mode')
  } else {
    document.documentElement.classList.remove('dark-mode')
  }
}

const handleUserCommand = (command: string) => {
  if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗?', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(async () => {
      await userStore.logout()
      router.push('/login')
    }).catch(() => {})
  } else if (command === 'profile') {
    router.push('/profile/index')
  } else if (command === 'password') {
    router.push('/profile/password')
  }
}

const handleNotificationCommand = (command: string) => {
  if (command === 'viewAll') {
    // Navigate to notifications page
    router.push('/notifications')
  } else {
    // Mark specific notification as read
    const notification = notifications.value.find(n => n.id === command)
    if (notification) {
      notification.read = true
    }
    // Show notification detail
    ElMessageBox.alert(notification?.message, notification?.title, {
      confirmButtonText: '确定'
    })
  }
}

const markAllAsRead = (e: Event) => {
  e.stopPropagation()
  notifications.value.forEach(n => {
    n.read = true
  })
}

const getNotificationIcon = (type: string) => {
  const iconMap = {
    success: SuccessFilled,
    warning: WarningFilled,
    info: InfoFilled,
    error: CircleCloseFilled
  }
  return iconMap[type] || InfoFilled
}

const formatTime = (date: Date) => {
  return formatDistanceToNow(date, { addSuffix: true, locale: zhCN })
}

// Responsive handler
const handleResize = () => {
  const rect = document.body.getBoundingClientRect()
  const width = rect.width
  
  if (width <= 992) {
    appStore.toggleDevice('mobile')
    appStore.closeSidebar()
  } else {
    appStore.toggleDevice('desktop')
    appStore.openSidebar()
  }
}

// Lifecycle
onMounted(() => {
  // Initialize theme
  if (isDark.value) {
    document.documentElement.classList.add('dark-mode')
  }
  
  // Add resize event listener
  window.addEventListener('resize', handleResize)
  handleResize()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
})

// Watch route changes to close sidebar on mobile
watch(
  () => route.path,
  () => {
    if (isMobile.value && sidebarVisible.value) {
      closeSidebar()
    }
  }
)
</script>

<style lang="scss" scoped>
// Variables
$sideBarWidth: 210px;
$collapsedWidth: 64px;
$headerHeight: 60px;

.app-wrapper {
  position: relative;
  height: 100vh;
  width: 100%;
  display: flex;
  
  // Sidebar
  .sidebar-container {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    width: $sideBarWidth;
    height: 100vh;
    background-color: var(--el-menu-bg-color);
    box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
    transition: width 0.28s;
    z-index: 1001;
    overflow: hidden;
    
    &.collapsed {
      width: $collapsedWidth;
    }
    
    .logo-container {
      height: $headerHeight;
      padding: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      
      .logo-full {
        height: 40px;
        max-width: 180px;
      }
      
      .logo-icon {
        height: 32px;
        width: 32px;
      }
    }
    
    .sidebar-toggle {
      position: absolute;
      bottom: 20px;
      left: 0;
      right: 0;
      display: flex;
      justify-content: center;
      align-items: center;
      height: 40px;
      cursor: pointer;
      color: var(--el-text-color-secondary);
      
      &:hover {
        color: var(--el-color-primary);
      }
      
      .is-active {
        transform: rotate(180deg);
      }
      
      .el-icon {
        font-size: 20px;
        transition: transform 0.3s;
      }
    }
  }
  
  // Mobile sidebar mask
  .sidebar-mask {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    z-index: 1000;
  }
  
  // Main container
  .main-container {
    flex: 1;
    min-height: 100vh;
    margin-left: $sideBarWidth;
    position: relative;
    background-color: var(--el-bg-color);
    transition: margin-left 0.28s;
    
    .header-container {
      position: fixed;
      top: 0;
      right: 0;
      left: $sideBarWidth;
      height: $headerHeight;
      padding: 0 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      background-color: var(--el-bg-color);
      box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
      z-index: 1000;
      transition: left 0.28s;
      
      .header-left {
        display: flex;
        align-items: center;
        
        .mobile-toggle {
          margin-right: 15px;
          font-size: 20px;
          cursor: pointer;
        }
      }
      
      .market-ticker {
        flex: 1;
        margin: 0 20px;
        overflow: hidden;
      }
      
      .header-right {
        display: flex;
        align-items: center;
        
        .ws-status {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          margin-right: 15px;
          cursor: pointer;
          
          &.connected {
            color: #67c23a;
          }
          
          &.disconnected {
            color: #f56c6c;
          }
        }
        
        .theme-toggle {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          margin-right: 15px;
          cursor: pointer;
          
          &:hover {
            background-color: var(--el-fill-color-light);
          }
        }
        
        .notification-icon {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          margin-right: 15px;
          cursor: pointer;
          
          &:hover {
            background-color: var(--el-fill-color-light);
          }
        }
        
        .user-info {
          display: flex;
          align-items: center;
          cursor: pointer;
          padding: 0 8px;
          border-radius: 4px;
          
          &:hover {
            background-color: var(--el-fill-color-light);
          }
          
          .username {
            margin: 0 8px;
            max-width: 100px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }
          
          .dropdown-icon {
            font-size: 12px;
            margin-left: 4px;
          }
        }
      }
    }
    
    .main-content {
      padding-top: $headerHeight;
      min-height: calc(100vh - #{$headerHeight});
      box-sizing: border-box;
    }
  }
  
  // When sidebar is collapsed
  &:not(.mobile) {
    .sidebar-container.collapsed + .main-container {
      margin-left: $collapsedWidth;
      
      .header-container {
        left: $collapsedWidth;
      }
    }
  }
  
  // Mobile mode
  &.mobile {
    .main-container {
      margin-left: 0;
      
      .header-container {
        left: 0;
      }
    }
    
    &.sidebar-hidden {
      .sidebar-container {
        transform: translateX(-100%);
      }
    }
    
    .sidebar-container {
      width: $sideBarWidth !important;
      transform: translateX(0);
      transition: transform 0.28s;
    }
  }
}

// Dropdown styles
:deep(.el-dropdown-menu) {
  .dropdown-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 16px;
    font-weight: bold;
  }
  
  .notification-item {
    display: flex;
    align-items: flex-start;
    padding: 8px 0;
    
    &.unread {
      background-color: var(--el-fill-color-light);
    }
    
    .notification-icon {
      margin-right: 8px;
      font-size: 16px;
      
      &.success {
        color: var(--el-color-success);
      }
      
      &.warning {
        color: var(--el-color-warning);
      }
      
      &.info {
        color: var(--el-color-info);
      }
      
      &.error {
        color: var(--el-color-danger);
      }
    }
    
    .notification-content {
      flex: 1;
      min-width: 200px;
      max-width: 300px;
      
      .notification-title {
        font-weight: bold;
        margin-bottom: 4px;
      }
      
      .notification-message {
        font-size: 12px;
        color: var(--el-text-color-regular);
        margin-bottom: 4px;
        word-break: break-word;
      }
      
      .notification-time {
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }
    }
  }
}

// Dark mode adaptations
:deep(.dark-mode) {
  .app-wrapper {
    .sidebar-container {
      background-color: #1f2937;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
    }
    
    .main-container {
      background-color: #111827;
      
      .header-container {
        background-color: #1f2937;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
      }
    }
  }
}
</style>
