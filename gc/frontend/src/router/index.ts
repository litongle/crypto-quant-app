import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { useUserStore } from '@/store/modules/user'
import { usePermissionStore } from '@/store/modules/permission'
import { ElMessage } from 'element-plus'

// 进度条配置
NProgress.configure({ 
  showSpinner: false,
  easing: 'ease',
  speed: 500 
})

// 路由元数据类型定义
declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    icon?: string
    hidden?: boolean
    roles?: string[]
    keepAlive?: boolean
    breadcrumb?: boolean
    activeMenu?: string
    noCache?: boolean
    affix?: boolean
  }
}

// 常量路由 - 不需要权限的基础路由
export const constantRoutes: Array<RouteRecordRaw> = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { 
      title: '登录',
      hidden: true 
    }
  },
  {
    path: '/404',
    name: 'NotFound',
    component: () => import('@/views/error-page/404.vue'),
    meta: { 
      title: '404',
      hidden: true 
    }
  },
  {
    path: '/401',
    name: 'Unauthorized',
    component: () => import('@/views/error-page/401.vue'),
    meta: { 
      title: '401',
      hidden: true 
    }
  },
  {
    path: '/',
    component: () => import('@/layout/index.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { 
          title: '仪表盘',
          icon: 'Odometer',
          affix: true 
        }
      }
    ]
  }
]

// 异步路由 - 需要根据权限动态加载的路由
export const asyncRoutes: Array<RouteRecordRaw> = [
  // 交易管理
  {
    path: '/trading',
    component: () => import('@/layout/index.vue'),
    redirect: '/trading/positions',
    name: 'Trading',
    meta: { 
      title: '交易管理',
      icon: 'TrendCharts',
      roles: ['admin', 'trader'] 
    },
    children: [
      {
        path: 'positions',
        name: 'Positions',
        component: () => import('@/views/trading/positions/index.vue'),
        meta: { 
          title: '持仓管理',
          icon: 'Position',
          keepAlive: true 
        }
      },
      {
        path: 'orders',
        name: 'Orders',
        component: () => import('@/views/trading/orders/index.vue'),
        meta: { 
          title: '订单管理',
          icon: 'List',
          keepAlive: true 
        }
      },
      {
        path: 'history',
        name: 'TradeHistory',
        component: () => import('@/views/trading/history/index.vue'),
        meta: { 
          title: '交易历史',
          icon: 'Histogram',
          keepAlive: true 
        }
      }
    ]
  },
  
  // 策略管理
  {
    path: '/strategy',
    component: () => import('@/layout/index.vue'),
    redirect: '/strategy/list',
    name: 'Strategy',
    meta: { 
      title: '策略管理',
      icon: 'SetUp',
      roles: ['admin', 'trader', 'viewer'] 
    },
    children: [
      {
        path: 'list',
        name: 'StrategyList',
        component: () => import('@/views/strategy/list/index.vue'),
        meta: { 
          title: '策略列表',
          icon: 'Menu',
          keepAlive: true 
        }
      },
      {
        path: 'create',
        name: 'StrategyCreate',
        component: () => import('@/views/strategy/create/index.vue'),
        meta: { 
          title: '创建策略',
          icon: 'Plus',
          roles: ['admin', 'trader']
        }
      },
      {
        path: 'detail/:id',
        name: 'StrategyDetail',
        component: () => import('@/views/strategy/detail/index.vue'),
        meta: { 
          title: '策略详情',
          icon: 'InfoFilled',
          activeMenu: '/strategy/list',
          hidden: true 
        }
      },
      {
        path: 'edit/:id',
        name: 'StrategyEdit',
        component: () => import('@/views/strategy/edit/index.vue'),
        meta: { 
          title: '编辑策略',
          icon: 'Edit',
          activeMenu: '/strategy/list',
          roles: ['admin', 'trader'],
          hidden: true 
        }
      },
      {
        path: 'backtest',
        name: 'Backtest',
        component: () => import('@/views/strategy/backtest/index.vue'),
        meta: { 
          title: '策略回测',
          icon: 'DataAnalysis',
          roles: ['admin', 'trader'] 
        }
      }
    ]
  },
  
  // 账户管理（相关页面未实现，暂时移除以避免构建错误）
  
  // 数据分析（相关页面未实现，暂时移除）
  
  // 系统管理
  {
    path: '/system',
    component: () => import('@/layout/index.vue'),
    redirect: '/system/user',
    name: 'System',
    meta: { 
      title: '系统管理',
      icon: 'Setting',
      roles: ['admin'] 
    },
    children: [
      {
        path: 'user',
        name: 'UserManagement',
        component: () => import('@/views/system/user/index.vue'),
        meta: { 
          title: '用户管理',
          icon: 'Avatar',
          keepAlive: true 
        }
      },
      {
        path: 'role',
        name: 'RoleManagement',
        component: () => import('@/views/system/role/index.vue'),
        meta: { 
          title: '角色管理',
          icon: 'UserFilled',
          keepAlive: true 
        }
      },
      {
        path: 'log',
        name: 'LogManagement',
        component: () => import('@/views/system/log/index.vue'),
        meta: { 
          title: '日志管理',
          icon: 'Document',
          keepAlive: true 
        }
      },
      {
        path: 'config',
        name: 'SystemConfig',
        component: () => import('@/views/system/config/index.vue'),
        meta: { 
          title: '系统配置',
          icon: 'Tools',
          keepAlive: true 
        }
      },
      {
        path: 'env',
        name: 'EnvConfig',
        component: () => import('@/views/system/env/index.vue'),
        meta: { 
          title: '环境变量配置',
          icon: 'Key',
          keepAlive: true 
        }
      },
      // 其余系统管理子路由暂未实现，先行注释
    ]
  },
  
  // 个人中心、帮助文档（相关页面暂未实现，移除）
  
  // 404 页面组件未实现，暂时不配置全局 404 路由
]

// 创建路由实例
const router = createRouter({
  history: createWebHistory(),
  routes: constantRoutes,
  // 平滑滚动
  scrollBehavior: (to, from, savedPosition) => {
    if (savedPosition) {
      return savedPosition
    } else {
      return { top: 0 }
    }
  }
})

// 白名单路由 - 不需要登录就可以访问
const whiteList = ['/login', '/auth-redirect', '/404', '/401']

// 全局前置守卫
router.beforeEach(async (to, from, next) => {
  // 开始进度条
  NProgress.start()
  
  // 设置页面标题
  document.title = to.meta.title ? `${to.meta.title} - RSI分层极值追踪量化系统` : 'RSI分层极值追踪量化系统'
  
  // 获取用户和权限存储
  const userStore = useUserStore()
  const permissionStore = usePermissionStore()
  
  // 判断用户是否已登录
  const hasToken = userStore.token
  
  if (hasToken) {
    if (to.path === '/login') {
      // 如果已登录，重定向到首页
      next({ path: '/' })
      NProgress.done()
    } else {
      // 判断用户是否已获取角色信息
      const hasRoles = userStore.roles && userStore.roles.length > 0
      
      if (hasRoles) {
        // 如果已有角色信息，直接访问
        next()
      } else {
        try {
          // 获取用户信息
          const { roles } = await userStore.getUserInfo()
          
          // 根据角色生成可访问路由
          const accessRoutes = await permissionStore.generateRoutes(roles)
          
          // 动态添加可访问路由
          accessRoutes.forEach(route => {
            router.addRoute(route)
          })
          
          // 重新导航到目标页面，确保路由已加载
          next({ ...to, replace: true })
        } catch (error) {
          // 重置token并跳转到登录页
          await userStore.resetToken()
          ElMessage.error('登录已过期，请重新登录')
          next(`/login?redirect=${to.path}`)
          NProgress.done()
        }
      }
    }
  } else {
    // 未登录
    if (whiteList.indexOf(to.path) !== -1) {
      // 在白名单中，直接访问
      next()
    } else {
      // 不在白名单中，重定向到登录页
      next(`/login?redirect=${to.path}`)
      NProgress.done()
    }
  }
})

// 全局后置守卫
router.afterEach(() => {
  // 结束进度条
  NProgress.done()
})

// 路由错误处理
router.onError((error) => {
  console.error('路由错误:', error)
  NProgress.done()
})

export default router
