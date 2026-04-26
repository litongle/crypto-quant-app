<template>
  <div v-if="!isHidden">
    <!-- If the route has children and should be shown as submenu -->
    <el-sub-menu v-if="showSubMenu" :index="resolvePath(item.path)" popper-append-to-body>
      <template #title>
        <el-icon v-if="item.meta && item.meta.icon">
          <component :is="item.meta.icon" />
        </el-icon>
        <span>{{ item.meta?.title }}</span>
      </template>
      
      <sidebar-item
        v-for="child in showingChildren"
        :key="child.path"
        :item="child"
        :base-path="resolvePath(child.path)"
        :is-collapsed="isCollapsed"
      />
    </el-sub-menu>
    
    <!-- If the route is a single menu item -->
    <template v-else>
      <el-menu-item
        v-if="item.meta && item.meta.title"
        :index="resolvePath(item.path)"
        @click="handleLink"
      >
        <el-tooltip
          v-if="isCollapsed"
          :content="item.meta.title"
          placement="right"
          :show-after="300"
        >
          <div>
            <el-icon v-if="item.meta && item.meta.icon">
              <component :is="item.meta.icon" />
            </el-icon>
            <span>{{ item.meta.title }}</span>
          </div>
        </el-tooltip>
        <template v-else>
          <el-icon v-if="item.meta && item.meta.icon">
            <component :is="item.meta.icon" />
          </el-icon>
          <span>{{ item.meta.title }}</span>
        </template>
      </el-menu-item>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, RouteRecordRaw } from 'vue-router'
import { isExternal } from '@/utils/validate'
import { useUserStore } from '@/store/modules/user'
import path from 'path-browserify'

// Props definition
interface Props {
  item: RouteRecordRaw
  basePath: string
  isCollapsed: boolean
}

const props = withDefaults(defineProps<Props>(), {
  basePath: '',
  isCollapsed: false
})

// Router and stores
const router = useRouter()
const userStore = useUserStore()

// Check if the route should be hidden
const isHidden = computed(() => {
  if (!props.item.meta) return false
  return props.item.meta.hidden === true
})

// Check if the user has permission to access this route
const hasPermission = computed(() => {
  if (!props.item.meta || !props.item.meta.roles) return true
  
  const { roles } = userStore
  return roles.some(role => (props.item.meta?.roles as string[]).includes(role))
})

// Check if the route has children that should be shown
const showingChildren = computed(() => {
  if (!props.item.children) return []
  
  return props.item.children.filter(child => {
    if (child.meta?.hidden) return false
    
    // Check role permissions for children
    if (child.meta?.roles && !child.meta.roles.some(role => userStore.roles.includes(role))) {
      return false
    }
    
    return true
  })
})

// Determine if this should be shown as a submenu
const showSubMenu = computed(() => {
  if (props.item.children) {
    const showingChildLen = showingChildren.value.length
    
    if (showingChildLen === 1 && !showingChildren.value[0].children) {
      // If there's only one child and it doesn't have children,
      // we could optionally flatten the menu structure here
      return false
    }
    
    if (showingChildLen > 0) {
      return true
    }
  }
  
  return false
})

// Resolve the full path by combining base path and current path
const resolvePath = (routePath: string) => {
  if (isExternal(routePath)) {
    return routePath
  }
  
  if (isExternal(props.basePath)) {
    return props.basePath
  }
  
  return path.resolve(props.basePath, routePath)
}

// Handle link click - for external links or router navigation
const handleLink = () => {
  const { path } = props.item
  
  if (isExternal(path)) {
    window.open(path, '_blank')
  } else {
    const fullPath = resolvePath(path)
    router.push(fullPath)
  }
}
</script>

<style lang="scss" scoped>
.el-menu-item, :deep(.el-sub-menu__title) {
  display: flex;
  align-items: center;
  
  .el-icon {
    margin-right: 16px;
    font-size: 18px;
  }
}

// Adjust spacing in collapsed mode
:deep(.el-menu--collapse) {
  .el-sub-menu__title {
    span {
      display: none;
    }
    
    .el-icon {
      margin: 0;
    }
  }
}
</style>
