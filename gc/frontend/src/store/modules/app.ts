import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// Define types for app state
export interface AppState {
  sidebar: {
    opened: boolean
    withoutAnimation: boolean
  }
  device: 'desktop' | 'mobile'
  theme: 'light' | 'dark'
  size: 'default' | 'large' | 'small'
  loading: boolean
  loadingText: string
  breakpoints: {
    xs: number
    sm: number
    md: number
    lg: number
    xl: number
  }
}

// Load state from localStorage
const loadFromStorage = <T>(key: string, defaultValue: T): T => {
  try {
    const value = localStorage.getItem(key)
    if (value) {
      return JSON.parse(value)
    }
  } catch (e) {
    console.error(`Error loading ${key} from localStorage:`, e)
  }
  return defaultValue
}

// Save state to localStorage
const saveToStorage = <T>(key: string, value: T): void => {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch (e) {
    console.error(`Error saving ${key} to localStorage:`, e)
  }
}

// Get system preference for dark mode
const getSystemThemePreference = (): 'light' | 'dark' => {
  if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark'
  }
  return 'light'
}

export const useAppStore = defineStore('app', () => {
  // State
  const sidebar = ref<AppState['sidebar']>(loadFromStorage('sidebar', {
    opened: true,
    withoutAnimation: false
  }))
  
  const device = ref<AppState['device']>(loadFromStorage('device', 'desktop'))
  
  const theme = ref<AppState['theme']>(loadFromStorage('theme', getSystemThemePreference()))
  
  const size = ref<AppState['size']>(loadFromStorage('size', 'default'))
  
  const loading = ref<boolean>(false)
  
  const loadingText = ref<string>('')
  
  const breakpoints = ref<AppState['breakpoints']>({
    xs: 576,
    sm: 768,
    md: 992,
    lg: 1200,
    xl: 1600
  })

  // Getters
  const isMobile = computed(() => device.value === 'mobile')
  
  const isDark = computed(() => theme.value === 'dark')
  
  const currentSize = computed(() => size.value)

  // Actions
  const toggleSidebar = (withoutAnimation?: boolean) => {
    sidebar.value.opened = !sidebar.value.opened
    sidebar.value.withoutAnimation = withoutAnimation || false
    saveToStorage('sidebar', sidebar.value)
  }
  
  const closeSidebar = (withoutAnimation?: boolean) => {
    sidebar.value.opened = false
    sidebar.value.withoutAnimation = withoutAnimation || false
    saveToStorage('sidebar', sidebar.value)
  }
  
  const openSidebar = (withoutAnimation?: boolean) => {
    sidebar.value.opened = true
    sidebar.value.withoutAnimation = withoutAnimation || false
    saveToStorage('sidebar', sidebar.value)
  }
  
  const toggleDevice = (val: AppState['device']) => {
    device.value = val
    saveToStorage('device', val)
  }
  
  const toggleTheme = () => {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    saveToStorage('theme', theme.value)
    
    // Apply theme to document
    if (theme.value === 'dark') {
      document.documentElement.classList.add('dark-mode')
    } else {
      document.documentElement.classList.remove('dark-mode')
    }
  }
  
  const setTheme = (val: AppState['theme']) => {
    theme.value = val
    saveToStorage('theme', val)
    
    // Apply theme to document
    if (theme.value === 'dark') {
      document.documentElement.classList.add('dark-mode')
    } else {
      document.documentElement.classList.remove('dark-mode')
    }
  }
  
  const setSize = (val: AppState['size']) => {
    size.value = val
    saveToStorage('size', val)
  }
  
  const startLoading = (text: string = '加载中...') => {
    loading.value = true
    loadingText.value = text
  }
  
  const stopLoading = () => {
    loading.value = false
    loadingText.value = ''
  }
  
  // Check if current screen width matches breakpoint
  const matchBreakpoint = (breakpoint: keyof AppState['breakpoints']) => {
    if (typeof window === 'undefined') return false
    return window.innerWidth >= breakpoints.value[breakpoint]
  }
  
  // Initialize theme based on system preference and listen for changes
  const initTheme = () => {
    // Apply initial theme
    if (theme.value === 'dark') {
      document.documentElement.classList.add('dark-mode')
    } else {
      document.documentElement.classList.remove('dark-mode')
    }
    
    // Listen for system theme changes
    if (window.matchMedia) {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
      
      const handleChange = (e: MediaQueryListEvent) => {
        // Only change theme if user hasn't explicitly set a preference
        if (!localStorage.getItem('theme')) {
          setTheme(e.matches ? 'dark' : 'light')
        }
      }
      
      // Add listener with modern API if available
      if (mediaQuery.addEventListener) {
        mediaQuery.addEventListener('change', handleChange)
      } else {
        // Fallback for older browsers
        mediaQuery.addListener(handleChange)
      }
    }
  }

  return {
    // State
    sidebar,
    device,
    theme,
    size,
    loading,
    loadingText,
    breakpoints,
    
    // Getters
    isMobile,
    isDark,
    currentSize,
    
    // Actions
    toggleSidebar,
    closeSidebar,
    openSidebar,
    toggleDevice,
    toggleTheme,
    setTheme,
    setSize,
    startLoading,
    stopLoading,
    matchBreakpoint,
    initTheme
  }
})
