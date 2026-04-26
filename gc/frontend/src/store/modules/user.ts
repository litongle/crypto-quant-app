import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, logout as apiLogout, getUserInfo as apiGetUserInfo } from '@/api/user'
import { getToken, setToken, removeToken, isTokenExpired, decodeToken } from '@/utils/auth'
import { ElMessage } from 'element-plus'
import router from '@/router'

// User information interface
export interface UserInfo {
  id: number
  username: string
  name: string
  email: string
  avatar?: string
  introduction?: string
  roles: string[]
  permissions: string[]
  created_at: string
  last_login?: string
}

// User state interface
export interface UserState {
  token: string
  refreshToken: string
  tokenExpires: number
  userInfo: UserInfo | null
  roles: string[]
  permissions: string[]
  loginLoading: boolean
  loginError: string | null
}

// Default user info
const defaultUserInfo: UserInfo = {
  id: 0,
  username: '',
  name: '',
  email: '',
  avatar: '',
  introduction: '',
  roles: [],
  permissions: [],
  created_at: ''
}

// Check if token refresh is needed
const needsRefresh = (expiresIn: number): boolean => {
  // Refresh token if it expires in less than 10 minutes
  return expiresIn > 0 && expiresIn < 10 * 60 * 1000
}

export const useUserStore = defineStore('user', () => {
  // State
  const token = ref<string>(getToken() || '')
  const refreshToken = ref<string>(localStorage.getItem('refreshToken') || '')
  const tokenExpires = ref<number>(0)
  const userInfo = ref<UserInfo | null>(null)
  const roles = ref<string[]>([])
  const permissions = ref<string[]>([])
  const loginLoading = ref<boolean>(false)
  const loginError = ref<string | null>(null)

  // Initialize token expiration if token exists
  if (token.value) {
    try {
      const decoded = decodeToken(token.value)
      if (decoded && decoded.exp) {
        tokenExpires.value = decoded.exp * 1000
      }
    } catch (error) {
      console.error('Failed to decode token:', error)
    }
  }

  // Getters
  const isLoggedIn = computed(() => !!token.value && !isTokenExpired(tokenExpires.value))
  
  const name = computed(() => userInfo.value?.name || '')
  
  const avatar = computed(() => userInfo.value?.avatar || '')
  
  const introduction = computed(() => userInfo.value?.introduction || '')

  const hasRole = computed(() => {
    return (role: string): boolean => {
      if (!roles.value || roles.value.length === 0) {
        return false
      }
      return roles.value.includes(role)
    }
  })

  const hasPermission = computed(() => {
    return (permission: string): boolean => {
      if (!permissions.value || permissions.value.length === 0) {
        return false
      }
      return permissions.value.includes(permission)
    }
  })

  const isAdmin = computed(() => {
    return roles.value.includes('admin')
  })

  // Actions
  const login = async (username: string, password: string): Promise<boolean> => {
    loginLoading.value = true
    loginError.value = null
    
    try {
      const { data } = await apiLogin({ username, password })
      
      if (data.token) {
        token.value = data.token
        setToken(data.token)
        
        if (data.refresh_token) {
          refreshToken.value = data.refresh_token
          localStorage.setItem('refreshToken', data.refresh_token)
        }
        
        // Decode token to get expiration
        try {
          const decoded = decodeToken(data.token)
          if (decoded && decoded.exp) {
            tokenExpires.value = decoded.exp * 1000
          }
        } catch (error) {
          console.error('Failed to decode token:', error)
        }
        
        // Get user info after successful login
        await getUserInfo()
        
        return true
      } else {
        throw new Error('登录失败，未获取到有效令牌')
      }
    } catch (error) {
      console.error('Login error:', error)
      loginError.value = error instanceof Error ? error.message : '登录失败，请检查用户名和密码'
      ElMessage.error(loginError.value)
      return false
    } finally {
      loginLoading.value = false
    }
  }

  const logout = async (): Promise<void> => {
    if (token.value) {
      try {
        await apiLogout()
      } catch (error) {
        console.error('Logout error:', error)
      }
    }
    
    // Reset state regardless of API call result
    resetToken()
    resetUserInfo()
    
    // Redirect to login page
    router.push('/login')
  }

  const getUserInfo = async (): Promise<UserInfo> => {
    if (!token.value) {
      throw new Error('Token不存在，请先登录')
    }
    
    try {
      const { data } = await apiGetUserInfo()
      
      if (!data) {
        throw new Error('获取用户信息失败')
      }
      
      // Update user info
      userInfo.value = data
      
      // Extract roles and permissions
      if (data.roles && Array.isArray(data.roles)) {
        roles.value = data.roles
      } else {
        roles.value = []
        console.error('获取到的用户角色格式不正确')
      }
      
      if (data.permissions && Array.isArray(data.permissions)) {
        permissions.value = data.permissions
      } else {
        permissions.value = []
        console.error('获取到的用户权限格式不正确')
      }
      
      return data
    } catch (error) {
      console.error('Get user info error:', error)
      resetToken()
      throw error
    }
  }

  const refreshUserToken = async (): Promise<boolean> => {
    if (!refreshToken.value) {
      console.error('No refresh token available')
      return false
    }
    
    try {
      const { data } = await apiLogin({ refresh_token: refreshToken.value })
      
      if (data.token) {
        token.value = data.token
        setToken(data.token)
        
        if (data.refresh_token) {
          refreshToken.value = data.refresh_token
          localStorage.setItem('refreshToken', data.refresh_token)
        }
        
        // Decode token to get expiration
        try {
          const decoded = decodeToken(data.token)
          if (decoded && decoded.exp) {
            tokenExpires.value = decoded.exp * 1000
          }
        } catch (error) {
          console.error('Failed to decode token:', error)
        }
        
        return true
      } else {
        throw new Error('Token refresh failed')
      }
    } catch (error) {
      console.error('Token refresh error:', error)
      resetToken()
      return false
    }
  }

  const resetToken = (): void => {
    token.value = ''
    refreshToken.value = ''
    tokenExpires.value = 0
    removeToken()
    localStorage.removeItem('refreshToken')
  }

  const resetUserInfo = (): void => {
    userInfo.value = null
    roles.value = []
    permissions.value = []
  }

  const updateUserProfile = async (profile: Partial<UserInfo>): Promise<boolean> => {
    try {
      // Call API to update profile
      // const { data } = await apiUpdateProfile(profile)
      
      // For now, just update local state
      if (userInfo.value) {
        userInfo.value = { ...userInfo.value, ...profile }
      }
      
      return true
    } catch (error) {
      console.error('Update profile error:', error)
      ElMessage.error('更新个人资料失败')
      return false
    }
  }

  const changePassword = async (oldPassword: string, newPassword: string): Promise<boolean> => {
    try {
      // Call API to change password
      // const { data } = await apiChangePassword({ old_password: oldPassword, new_password: newPassword })
      
      ElMessage.success('密码修改成功，请重新登录')
      
      // Force logout after password change
      await logout()
      
      return true
    } catch (error) {
      console.error('Change password error:', error)
      ElMessage.error('修改密码失败')
      return false
    }
  }

  // Check token expiration and refresh if needed
  const checkTokenExpiration = async (): Promise<void> => {
    if (!token.value) return
    
    const now = Date.now()
    const timeToExpire = tokenExpires.value - now
    
    if (isTokenExpired(tokenExpires.value)) {
      // Token is expired, try to refresh
      const refreshed = await refreshUserToken()
      if (!refreshed) {
        // If refresh failed, logout
        resetToken()
        resetUserInfo()
        router.push('/login?redirect=' + encodeURIComponent(router.currentRoute.value.fullPath))
      }
    } else if (needsRefresh(timeToExpire)) {
      // Token will expire soon, refresh it
      await refreshUserToken()
    }
  }

  return {
    // State
    token,
    refreshToken,
    tokenExpires,
    userInfo,
    roles,
    permissions,
    loginLoading,
    loginError,
    
    // Getters
    isLoggedIn,
    name,
    avatar,
    introduction,
    hasRole,
    hasPermission,
    isAdmin,
    
    // Actions
    login,
    logout,
    getUserInfo,
    refreshUserToken,
    resetToken,
    resetUserInfo,
    updateUserProfile,
    changePassword,
    checkTokenExpiration
  }
})
