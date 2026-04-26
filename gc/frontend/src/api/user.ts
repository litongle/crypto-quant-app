import axios, { AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import { 
  getToken, 
  setToken, 
  removeToken, 
  getRefreshToken, 
  setRefreshToken, 
  removeRefreshToken,
  storeAuthData,
  clearAuthData
} from '@/utils/auth'

// Base API configuration
const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'
const api = axios.create({
  baseURL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor for API calls
api.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor for API calls
api.interceptors.response.use(
  (response) => {
    return response
  },
  async (error) => {
    const { response, config } = error
    
    // Handle token expiration and refresh
    if (response && response.status === 401 && !config._retry) {
      // Try to refresh the token
      const refreshToken = getRefreshToken()
      
      if (refreshToken) {
        try {
          config._retry = true
          const { data } = await refreshUserToken(refreshToken)
          
          if (data && data.token) {
            storeAuthData(data)
            
            // Retry the original request with new token
            config.headers['Authorization'] = `Bearer ${data.token}`
            return api(config)
          }
        } catch (refreshError) {
          console.error('Token refresh failed:', refreshError)
          // If refresh fails, clear auth data and redirect to login
          clearAuthData()
          ElMessage.error('登录已过期，请重新登录')
          window.location.href = '/login'
          return Promise.reject(refreshError)
        }
      }
    }
    
    if (response && response.status) {
      switch (response.status) {
        case 400:
          ElMessage.error(response.data?.message || '请求参数错误')
          break
        case 401:
          ElMessage.error('未授权，请重新登录')
          // Only redirect if not already on login page
          if (!window.location.pathname.includes('login')) {
            window.location.href = '/login'
          }
          break
        case 403:
          ElMessage.error('没有权限访问该资源')
          break
        case 404:
          ElMessage.error('请求的资源不存在')
          break
        case 500:
          ElMessage.error('服务器错误，请稍后再试')
          break
        default:
          ElMessage.error(response.data?.message || '请求失败')
      }
    } else {
      // Network error
      ElMessage.error('网络错误，请检查您的网络连接')
    }
    
    return Promise.reject(error)
  }
)

// ===== TypeScript Interfaces =====

/**
 * Login request parameters
 */
export interface LoginParams {
  username?: string
  password?: string
  refresh_token?: string
  remember_me?: boolean
}

/**
 * Login response data
 */
export interface LoginResponse {
  token: string
  refresh_token: string
  expires_in: number
  token_type: string
}

/**
 * User information
 */
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
  preferences?: UserPreferences
}

/**
 * User preferences
 */
export interface UserPreferences {
  theme?: 'light' | 'dark'
  language?: string
  notifications?: {
    email: boolean
    push: boolean
    sms: boolean
  }
  trading?: {
    defaultLeverage: number
    riskLevel: 'low' | 'medium' | 'high'
    autoConfirm: boolean
  }
  display?: {
    compactMode: boolean
    showBalance: boolean
    chartType: 'candle' | 'line' | 'area'
  }
}

/**
 * User profile update parameters
 */
export interface UpdateProfileParams {
  name?: string
  email?: string
  avatar?: string
  introduction?: string
}

/**
 * Password change parameters
 */
export interface ChangePasswordParams {
  old_password: string
  new_password: string
  confirm_password: string
}

/**
 * Password reset request parameters
 */
export interface ResetPasswordRequestParams {
  email: string
}

/**
 * Password reset confirmation parameters
 */
export interface ResetPasswordConfirmParams {
  token: string
  new_password: string
  confirm_password: string
}

/**
 * Registration parameters
 */
export interface RegisterParams {
  username: string
  name: string
  email: string
  password: string
  confirm_password: string
  invite_code?: string
}

// ===== API Functions =====

/**
 * User login
 * @param data Login parameters
 * @returns Login response with token
 */
export const login = async (data: LoginParams): Promise<AxiosResponse<LoginResponse>> => {
  try {
    return await api.post('/v1/auth/login', data)
  } catch (error) {
    console.error('Login failed:', error)
    throw error
  }
}

/**
 * User logout
 * @returns Success status
 */
export const logout = async (): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post('/v1/auth/logout')
  } catch (error) {
    console.error('Logout failed:', error)
    // Clear auth data regardless of API success
    clearAuthData()
    throw error
  }
}

/**
 * Get current user information
 * @returns User information
 */
export const getUserInfo = async (): Promise<AxiosResponse<UserInfo>> => {
  try {
    return await api.get('/v1/users/me')
  } catch (error) {
    console.error('Failed to get user info:', error)
    throw error
  }
}

/**
 * Update user profile
 * @param data Profile update parameters
 * @returns Updated user information
 */
export const updateProfile = async (data: UpdateProfileParams): Promise<AxiosResponse<UserInfo>> => {
  try {
    return await api.patch('/v1/users/profile', data)
  } catch (error) {
    console.error('Failed to update profile:', error)
    throw error
  }
}

/**
 * Change user password
 * @param data Password change parameters
 * @returns Success status
 */
export const changePassword = async (data: ChangePasswordParams): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post('/v1/users/change-password', data)
  } catch (error) {
    console.error('Failed to change password:', error)
    throw error
  }
}

/**
 * Refresh user token
 * @param refreshToken Refresh token
 * @returns New token response
 */
export const refreshUserToken = async (refreshToken: string): Promise<AxiosResponse<LoginResponse>> => {
  try {
    return await api.post('/v1/auth/refresh', { refresh_token: refreshToken })
  } catch (error) {
    console.error('Token refresh failed:', error)
    throw error
  }
}

/**
 * Register new user
 * @param data Registration parameters
 * @returns Registration response with user info
 */
export const register = async (data: RegisterParams): Promise<AxiosResponse<{ user: UserInfo, token: string }>> => {
  try {
    return await api.post('/v1/auth/register', data)
  } catch (error) {
    console.error('Registration failed:', error)
    throw error
  }
}

/**
 * Request password reset
 * @param data Password reset request parameters
 * @returns Success status
 */
export const requestPasswordReset = async (data: ResetPasswordRequestParams): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post('/v1/auth/forgot-password', data)
  } catch (error) {
    console.error('Password reset request failed:', error)
    throw error
  }
}

/**
 * Confirm password reset
 * @param data Password reset confirmation parameters
 * @returns Success status
 */
export const confirmPasswordReset = async (data: ResetPasswordConfirmParams): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post('/v1/auth/reset-password', data)
  } catch (error) {
    console.error('Password reset confirmation failed:', error)
    throw error
  }
}

/**
 * Verify email address
 * @param token Verification token
 * @returns Success status
 */
export const verifyEmail = async (token: string): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post('/v1/auth/verify-email', { token })
  } catch (error) {
    console.error('Email verification failed:', error)
    throw error
  }
}

/**
 * Get user preferences
 * @returns User preferences
 */
export const getUserPreferences = async (): Promise<AxiosResponse<UserPreferences>> => {
  try {
    return await api.get('/v1/users/preferences')
  } catch (error) {
    console.error('Failed to get user preferences:', error)
    throw error
  }
}

/**
 * Update user preferences
 * @param data User preferences
 * @returns Updated user preferences
 */
export const updateUserPreferences = async (data: Partial<UserPreferences>): Promise<AxiosResponse<UserPreferences>> => {
  try {
    return await api.patch('/v1/users/preferences', data)
  } catch (error) {
    console.error('Failed to update user preferences:', error)
    throw error
  }
}

/**
 * Check if username exists
 * @param username Username to check
 * @returns Whether username exists
 */
export const checkUsernameExists = async (username: string): Promise<AxiosResponse<{ exists: boolean }>> => {
  try {
    return await api.get('/v1/auth/check-username', {
      params: { username }
    })
  } catch (error) {
    console.error('Username check failed:', error)
    throw error
  }
}

/**
 * Check if email exists
 * @param email Email to check
 * @returns Whether email exists
 */
export const checkEmailExists = async (email: string): Promise<AxiosResponse<{ exists: boolean }>> => {
  try {
    return await api.get('/v1/auth/check-email', {
      params: { email }
    })
  } catch (error) {
    console.error('Email check failed:', error)
    throw error
  }
}

/**
 * Upload user avatar
 * @param file Avatar file
 * @returns URL of uploaded avatar
 */
export const uploadAvatar = async (file: File): Promise<AxiosResponse<{ url: string }>> => {
  try {
    const formData = new FormData()
    formData.append('avatar', file)
    
    return await api.post('/v1/users/avatar', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  } catch (error) {
    console.error('Avatar upload failed:', error)
    throw error
  }
}

/**
 * Get user activity log
 * @param page Page number
 * @param limit Items per page
 * @returns User activity log
 */
export const getUserActivityLog = async (page: number = 1, limit: number = 20): Promise<AxiosResponse<any>> => {
  try {
    return await api.get('/v1/users/activity-log', {
      params: { page, limit }
    })
  } catch (error) {
    console.error('Failed to get user activity log:', error)
    throw error
  }
}

export default api
