<template>
  <section class="app-main">
    <div v-if="loading" class="app-loading-container">
      <el-spin class="app-loading" />
    </div>
    
    <div v-else-if="error" class="app-error-container">
      <el-result
        icon="error"
        title="页面加载错误"
        :sub-title="errorMessage"
      >
        <template #extra>
          <el-button type="primary" @click="retryLoading">重试</el-button>
          <el-button @click="goHome">返回首页</el-button>
        </template>
      </el-result>
    </div>
    
    <div v-else class="app-content-container">
      <transition
        name="fade-transform"
        mode="out-in"
        @before-leave="beforeLeave"
        @after-leave="afterLeave"
      >
        <keep-alive v-if="keepAlive" :include="cachedViews">
          <router-view v-slot="{ Component, route }">
            <component
              :is="Component"
              :key="route.path"
              v-if="Component"
              @error-occurred="handleComponentError"
            />
          </router-view>
        </keep-alive>
        <router-view v-else v-slot="{ Component, route }">
          <component
            :is="Component"
            :key="route.path"
            v-if="Component"
            @error-occurred="handleComponentError"
          />
        </router-view>
      </transition>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onErrorCaptured, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/store/modules/app'

// Router
const route = useRoute()
const router = useRouter()

// App store
const appStore = useAppStore()

// State
const loading = ref(false)
const error = ref(false)
const errorMessage = ref('')
const cachedViews = ref<string[]>([])

// Computed properties
const keepAlive = computed(() => {
  return route.meta.keepAlive === true
})

// Methods
const beforeLeave = () => {
  // Reset scroll position
  window.scrollTo(0, 0)
}

const afterLeave = () => {
  // Update cached views if needed
  updateCachedViews()
}

const updateCachedViews = () => {
  // Get all routes with keepAlive meta
  const routes = router.getRoutes()
  const views = routes
    .filter(route => route.meta?.keepAlive)
    .map(route => route.name)
    .filter(Boolean) as string[]
  
  cachedViews.value = views
}

const handleComponentError = (err: Error) => {
  console.error('Component error:', err)
  error.value = true
  errorMessage.value = err.message || '组件加载失败'
  ElMessage.error('页面组件加载失败')
}

const retryLoading = async () => {
  error.value = false
  errorMessage.value = ''
  loading.value = true
  
  try {
    await router.replace(route.fullPath)
    await nextTick()
    loading.value = false
  } catch (err) {
    error.value = true
    errorMessage.value = err instanceof Error ? err.message : '重试加载失败'
    loading.value = false
  }
}

const goHome = () => {
  error.value = false
  errorMessage.value = ''
  router.push('/')
}

// Error boundary
onErrorCaptured((err, instance, info) => {
  console.error('Error captured in AppMain:', err, info)
  error.value = true
  errorMessage.value = err.message || '页面组件错误'
  ElMessage.error('页面发生错误')
  return false // Prevent error from propagating
})

// Navigation loading
const startLoading = () => {
  loading.value = true
  error.value = false
}

const endLoading = () => {
  loading.value = false
}

// Watch for route changes
watch(
  () => route.path,
  async () => {
    // Reset error state on route change
    error.value = false
    errorMessage.value = ''
  }
)

// Setup navigation guards for loading state
router.beforeEach((to, from, next) => {
  // Don't show loading for same-page navigation
  if (to.path !== from.path) {
    startLoading()
  }
  next()
})

router.afterEach(() => {
  // Small delay to prevent flashing
  setTimeout(() => {
    endLoading()
  }, 200)
})

// Initialize
onMounted(() => {
  updateCachedViews()
})
</script>

<style lang="scss" scoped>
.app-main {
  position: relative;
  width: 100%;
  min-height: calc(100vh - 60px);
  padding: 16px;
  box-sizing: border-box;
  overflow-x: hidden;
  
  .app-loading-container {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 200px;
    width: 100%;
  }
  
  .app-error-container {
    padding: 20px;
    width: 100%;
  }
  
  .app-content-container {
    width: 100%;
  }
}

// Responsive padding
@media (max-width: 768px) {
  .app-main {
    padding: 12px;
  }
}

@media (max-width: 576px) {
  .app-main {
    padding: 8px;
  }
}

// Page transition animations
.fade-transform-enter-active,
.fade-transform-leave-active {
  transition: all 0.3s;
}

.fade-transform-enter-from {
  opacity: 0;
  transform: translateX(30px);
}

.fade-transform-leave-to {
  opacity: 0;
  transform: translateX(-30px);
}

// Dark mode adaptations
:deep(.dark-mode) {
  .app-main {
    background-color: #111827;
  }
}
</style>
