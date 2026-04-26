import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { RouteRecordRaw } from 'vue-router'
import { constantRoutes, asyncRoutes } from '@/router'
import { useUserStore } from './user'

// TypeScript interfaces for route permissions
export interface PermissionState {
  routes: RouteRecordRaw[]
  dynamicRoutes: RouteRecordRaw[]
  currentRoute: RouteRecordRaw | null
}

/**
 * Check if the user has permission to access the route
 * @param roles User roles
 * @param route Route to check
 * @returns Whether the user has permission
 */
const hasPermission = (roles: string[], route: RouteRecordRaw): boolean => {
  if (route.meta && route.meta.roles) {
    // Check if user has any of the required roles
    return roles.some(role => (route.meta?.roles as string[]).includes(role))
  }
  
  // If no roles are specified in the route, everyone can access it
  return true
}

/**
 * Filter routes recursively based on user roles
 * @param routes Routes to filter
 * @param roles User roles
 * @returns Filtered routes
 */
const filterAsyncRoutes = (routes: RouteRecordRaw[], roles: string[]): RouteRecordRaw[] => {
  const result: RouteRecordRaw[] = []
  
  routes.forEach(route => {
    // Create a copy of the route to avoid modifying the original
    const routeCopy = { ...route }
    
    // Check if user has permission to access this route
    if (hasPermission(roles, routeCopy)) {
      // If the route has children, filter them recursively
      if (routeCopy.children && routeCopy.children.length > 0) {
        routeCopy.children = filterAsyncRoutes(routeCopy.children, roles)
        
        // Only add routes with children if they have at least one accessible child
        if (routeCopy.children.length > 0) {
          result.push(routeCopy)
        }
      } else {
        // If the route has no children, add it directly
        result.push(routeCopy)
      }
    }
  })
  
  return result
}

export const usePermissionStore = defineStore('permission', () => {
  // State
  const routes = ref<RouteRecordRaw[]>([])
  const dynamicRoutes = ref<RouteRecordRaw[]>([])
  const currentRoute = ref<RouteRecordRaw | null>(null)
  
  // Getters
  const hasRoutes = computed(() => routes.value.length > 0)
  
  const menuRoutes = computed(() => {
    // Filter out routes with hidden: true in meta
    return routes.value.filter(route => {
      return !(route.meta?.hidden)
    })
  })
  
  const isRouteAccessible = computed(() => {
    return (routePath: string): boolean => {
      // Check if the route exists in the accessible routes
      const findRoute = (routeList: RouteRecordRaw[], path: string): boolean => {
        for (const route of routeList) {
          if (route.path === path) {
            return true
          }
          if (route.children) {
            if (findRoute(route.children, path)) {
              return true
            }
          }
        }
        return false
      }
      
      return findRoute(routes.value, routePath)
    }
  })
  
  // Actions
  /**
   * Generate routes based on user roles
   * @param roles User roles
   * @returns Accessible routes
   */
  const generateRoutes = async (roles: string[]): Promise<RouteRecordRaw[]> => {
    let accessibleRoutes: RouteRecordRaw[] = []
    
    // If user is admin, they can access all routes
    if (roles.includes('admin')) {
      accessibleRoutes = asyncRoutes
    } else {
      // Otherwise, filter routes based on roles
      accessibleRoutes = filterAsyncRoutes(asyncRoutes, roles)
    }
    
    // Combine constant routes and dynamic routes
    routes.value = [...constantRoutes, ...accessibleRoutes]
    dynamicRoutes.value = accessibleRoutes
    
    return accessibleRoutes
  }
  
  /**
   * Set the current active route
   * @param route Current route
   */
  const setCurrentRoute = (route: RouteRecordRaw | null): void => {
    currentRoute.value = route
  }
  
  /**
   * Reset permission state
   */
  const resetRoutes = (): void => {
    routes.value = []
    dynamicRoutes.value = []
    currentRoute.value = null
  }
  
  /**
   * Check if a specific permission is required for a route
   * @param routePath Route path
   * @param permission Permission to check
   * @returns Whether the permission is required
   */
  const isPermissionRequired = (routePath: string, permission: string): boolean => {
    // Find the route by path
    const findRoute = (routeList: RouteRecordRaw[], path: string): RouteRecordRaw | null => {
      for (const route of routeList) {
        if (route.path === path) {
          return route
        }
        if (route.children) {
          const childRoute = findRoute(route.children, path)
          if (childRoute) {
            return childRoute
          }
        }
      }
      return null
    }
    
    const route = findRoute(routes.value, routePath)
    if (!route || !route.meta || !route.meta.permissions) {
      return false
    }
    
    return (route.meta.permissions as string[]).includes(permission)
  }
  
  /**
   * Check if user can access a specific route with required permissions
   * @param routePath Route path
   * @param requiredPermissions Required permissions
   * @returns Whether the user can access the route
   */
  const canAccessRoute = (routePath: string, requiredPermissions?: string[]): boolean => {
    // If no specific permissions are required, check if route is accessible
    if (!requiredPermissions || requiredPermissions.length === 0) {
      return isRouteAccessible.value(routePath)
    }
    
    // Check if user has all required permissions
    const userStore = useUserStore()
    return requiredPermissions.every(permission => userStore.hasPermission(permission))
  }

  return {
    // State
    routes,
    dynamicRoutes,
    currentRoute,
    
    // Getters
    hasRoutes,
    menuRoutes,
    isRouteAccessible,
    
    // Actions
    generateRoutes,
    setCurrentRoute,
    resetRoutes,
    isPermissionRequired,
    canAccessRoute
  }
})
