<template>
  <el-breadcrumb class="app-breadcrumb" separator="/">
    <transition-group name="breadcrumb">
      <el-breadcrumb-item v-for="(item, index) in breadcrumbs" :key="item.path">
        <span
          v-if="index === breadcrumbs.length - 1 || !item.redirect"
          class="no-redirect"
          :class="{ 'last-item': index === breadcrumbs.length - 1 }"
        >
          {{ item.title }}
        </span>
        <a v-else @click.prevent="handleLink(item)">{{ item.title }}</a>
      </el-breadcrumb-item>
    </transition-group>
  </el-breadcrumb>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter, RouteLocationMatched } from 'vue-router'
import { compile } from 'path-to-regexp'

// Router
const route = useRoute()
const router = useRouter()

// Breadcrumb items
interface BreadcrumbItem {
  path: string
  title: string
  redirect?: string
}

const breadcrumbs = ref<BreadcrumbItem[]>([])

// Get matched routes and filter out hidden routes
const getBreadcrumbs = () => {
  // Filter out routes with hidden: true in meta
  const matched = route.matched.filter(item => {
    return !(item.meta?.hidden)
  })
  
  const result: BreadcrumbItem[] = []
  
  // Always include home as first item
  const homeItem = {
    path: '/dashboard',
    title: '首页',
    redirect: '/dashboard'
  }
  
  // Only add home if we're not already on the dashboard
  if (route.path !== '/dashboard') {
    result.push(homeItem)
  }
  
  // Process matched routes
  matched.forEach(item => {
    // Skip routes without meta or title
    if (!item.meta || !item.meta.title) {
      return
    }
    
    // Handle dynamic route params
    const path = resolvePath(item)
    
    // Add to breadcrumb items
    result.push({
      path,
      title: item.meta.title as string,
      redirect: item.redirect
    })
  })
  
  return result
}

// Resolve dynamic route paths with actual params
const resolvePath = (route: RouteLocationMatched): string => {
  const { path } = route
  
  // Check if the route has params
  if (Object.keys(route.params).length === 0) {
    return path
  }
  
  // Compile the path with params
  const toPath = compile(path)
  return toPath(route.params)
}

// Handle breadcrumb link click
const handleLink = (item: BreadcrumbItem) => {
  if (item.redirect) {
    router.push(item.redirect)
  } else {
    router.push(item.path)
  }
}

// Update breadcrumbs when route changes
const updateBreadcrumbs = () => {
  breadcrumbs.value = getBreadcrumbs()
}

// Initialize breadcrumbs
updateBreadcrumbs()

// Watch for route changes
watch(
  () => route.path,
  () => {
    updateBreadcrumbs()
  }
)
</script>

<style lang="scss" scoped>
.app-breadcrumb {
  display: inline-block;
  font-size: 14px;
  line-height: 50px;
  margin-left: 8px;
  
  .no-redirect {
    color: var(--el-text-color-regular);
    cursor: text;
    
    &.last-item {
      color: var(--el-text-color-primary);
      font-weight: 500;
    }
  }
  
  a {
    color: var(--el-color-primary);
    cursor: pointer;
    
    &:hover {
      color: var(--el-color-primary-light-3);
    }
  }
}

// Breadcrumb animation
.breadcrumb-enter-active,
.breadcrumb-leave-active {
  transition: all 0.5s;
}

.breadcrumb-enter-from,
.breadcrumb-leave-active {
  opacity: 0;
  transform: translateX(20px);
}

.breadcrumb-leave-active {
  position: absolute;
}

// Responsive adjustments
@media (max-width: 768px) {
  .app-breadcrumb {
    font-size: 12px;
    line-height: 40px;
  }
}
</style>
