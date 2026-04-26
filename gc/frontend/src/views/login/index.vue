<template>
  <div class="login-container" :class="{ 'dark-mode': isDark }">
    <!-- Background animation -->
    <div class="background-animation">
      <div class="trading-chart"></div>
      <div class="particles-container">
        <div v-for="i in 20" :key="i" class="particle"></div>
      </div>
    </div>

    <!-- Login card -->
    <div class="login-card-container">
      <el-card class="login-card" shadow="always">
        <!-- Logo and title -->
        <div class="login-header">
          <img src="@/assets/logo-full.png" alt="RSI Tracker" class="login-logo">
          <h2 class="login-title">RSI分层极值追踪量化系统</h2>
          <p class="login-subtitle">专业的量化交易解决方案</p>
        </div>

        <!-- Login form -->
        <el-form
          ref="loginFormRef"
          :model="loginForm"
          :rules="loginRules"
          label-position="top"
          @keyup.enter="handleLogin"
        >
          <el-form-item prop="username">
            <el-input
              v-model="loginForm.username"
              placeholder="用户名"
              prefix-icon="User"
              :disabled="loginLoading"
              clearable
              autofocus
            />
          </el-form-item>

          <el-form-item prop="password">
            <el-input
              v-model="loginForm.password"
              :type="passwordVisible ? 'text' : 'password'"
              placeholder="密码"
              prefix-icon="Lock"
              :disabled="loginLoading"
              clearable
            >
              <template #suffix>
                <el-icon 
                  class="password-toggle" 
                  @click="passwordVisible = !passwordVisible"
                >
                  <component :is="passwordVisible ? 'View' : 'Hide'" />
                </el-icon>
              </template>
            </el-input>
          </el-form-item>

          <div class="login-options">
            <el-checkbox v-model="rememberMe" :disabled="loginLoading">记住我</el-checkbox>
            <el-link type="primary" :underline="false" href="#" @click.prevent="forgotPassword">忘记密码?</el-link>
          </div>

          <el-form-item>
            <el-button
              type="primary"
              class="login-button"
              :loading="loginLoading"
              @click="handleLogin"
            >
              登录
            </el-button>
          </el-form-item>
        </el-form>

        <!-- Error message -->
        <div v-if="loginError" class="login-error">
          <el-alert
            :title="loginError"
            type="error"
            show-icon
            :closable="false"
          />
        </div>

        <!-- Demo account notice -->
        <div class="demo-notice">
          <el-alert
            title="演示账号: admin / admin123"
            type="info"
            description="本系统支持演示账号登录，您可以使用上述账号体验系统功能。"
            show-icon
          />
        </div>

        <!-- Footer -->
        <div class="login-footer">
          <div class="theme-switch" @click="toggleTheme">
            <el-icon><component :is="isDark ? 'Sunny' : 'Moon'" /></el-icon>
            <span>{{ isDark ? '切换到亮色模式' : '切换到暗色模式' }}</span>
          </div>
          <div class="version-info">
            版本: v1.0.0 | &copy; {{ currentYear }} RSI Tracker
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ElMessage, FormInstance, FormRules } from 'element-plus'
import { User, Lock, View, Hide, Moon, Sunny } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/modules/user'
import { useAppStore } from '@/store/modules/app'

// Router
const router = useRouter()
const route = useRoute()

// Stores
const userStore = useUserStore()
const appStore = useAppStore()
const { loginLoading, loginError } = storeToRefs(userStore)
const { isDark } = storeToRefs(appStore)

// Form refs
const loginFormRef = ref<FormInstance>()

// Form data
const loginForm = reactive({
  username: '',
  password: ''
})

// Password visibility toggle
const passwordVisible = ref(false)

// Remember me checkbox
const rememberMe = ref(false)

// Current year for copyright
const currentYear = computed(() => new Date().getFullYear())

// Form validation rules
const loginRules = reactive<FormRules>({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度应为3-20个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 30, message: '密码长度应为6-30个字符', trigger: 'blur' }
  ]
})

// Toggle theme
const toggleTheme = () => {
  appStore.toggleTheme()
}

// Handle forgot password
const forgotPassword = () => {
  ElMessage.info('请联系系统管理员重置密码')
}

// Handle login
const handleLogin = async () => {
  if (!loginFormRef.value) return
  
  await loginFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        // Save credentials if remember me is checked
        if (rememberMe.value) {
          localStorage.setItem('remembered_username', loginForm.username)
        } else {
          localStorage.removeItem('remembered_username')
        }
        
        // Login
        const success = await userStore.login(loginForm.username, loginForm.password)
        
        if (success) {
          ElMessage.success('登录成功')
          
          // Redirect to the original requested page or dashboard
          const redirect = route.query.redirect as string
          router.replace(redirect || '/')
        }
      } catch (error) {
        console.error('Login error:', error)
      }
    } else {
      return false
    }
  })
}

// Load remembered username on mount
onMounted(() => {
  const rememberedUsername = localStorage.getItem('remembered_username')
  if (rememberedUsername) {
    loginForm.username = rememberedUsername
    rememberMe.value = true
  }
  
  // Initialize theme
  appStore.initTheme()
  
  // Focus username field
  setTimeout(() => {
    const usernameInput = document.querySelector('.login-container input[type="text"]') as HTMLInputElement
    if (usernameInput) {
      usernameInput.focus()
    }
  }, 500)
})
</script>

<style lang="scss" scoped>
.login-container {
  position: relative;
  width: 100vw;
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #1a365d 0%, #2d3748 100%);
  overflow: hidden;
  
  // Background animation elements
  .background-animation {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 0;
    opacity: 0.4;
    
    .trading-chart {
      position: absolute;
      bottom: 0;
      left: 0;
      width: 100%;
      height: 40%;
      background: linear-gradient(180deg, 
        rgba(72, 187, 120, 0.1) 0%,
        rgba(72, 187, 120, 0) 100%);
      mask-image: url('@/assets/chart-mask.svg');
      mask-size: cover;
      mask-repeat: no-repeat;
      animation: chartAnimation 15s infinite alternate;
    }
    
    .particles-container {
      position: absolute;
      width: 100%;
      height: 100%;
      
      .particle {
        position: absolute;
        width: 6px;
        height: 6px;
        background-color: rgba(255, 255, 255, 0.5);
        border-radius: 50%;
        
        @for $i from 1 through 20 {
          &:nth-child(#{$i}) {
            left: random(100) * 1%;
            top: random(100) * 1%;
            opacity: (random(10) * 0.1);
            animation: float #{random(20) + 10}s infinite ease-in-out;
            animation-delay: #{random(10)}s;
          }
        }
      }
    }
  }
  
  // Login card
  .login-card-container {
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 420px;
    padding: 20px;
    
    .login-card {
      border-radius: 8px;
      backdrop-filter: blur(10px);
      background-color: rgba(255, 255, 255, 0.95);
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
      transition: all 0.3s ease;
      
      &:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 35px rgba(0, 0, 0, 0.25);
      }
      
      .login-header {
        text-align: center;
        margin-bottom: 30px;
        
        .login-logo {
          height: 60px;
          margin-bottom: 15px;
        }
        
        .login-title {
          font-size: 22px;
          font-weight: 600;
          margin: 0 0 5px;
          color: var(--el-text-color-primary);
        }
        
        .login-subtitle {
          font-size: 14px;
          color: var(--el-text-color-secondary);
          margin: 0;
        }
      }
      
      .login-options {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
      }
      
      .login-button {
        width: 100%;
        height: 40px;
        font-size: 16px;
        font-weight: 500;
      }
      
      .login-error {
        margin: 20px 0;
      }
      
      .demo-notice {
        margin: 20px 0;
      }
      
      .login-footer {
        margin-top: 30px;
        padding-top: 20px;
        border-top: 1px solid var(--el-border-color-lighter);
        
        .theme-switch {
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          padding: 8px;
          border-radius: 4px;
          margin-bottom: 15px;
          
          &:hover {
            background-color: var(--el-fill-color-light);
          }
          
          .el-icon {
            margin-right: 8px;
          }
        }
        
        .version-info {
          text-align: center;
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }
      }
    }
  }
  
  // Password toggle icon
  .password-toggle {
    cursor: pointer;
    color: var(--el-text-color-secondary);
    
    &:hover {
      color: var(--el-text-color-primary);
    }
  }
  
  // Dark mode styles
  &.dark-mode {
    background: linear-gradient(135deg, #1a202c 0%, #2d3748 100%);
    
    .login-card {
      background-color: rgba(26, 32, 44, 0.95);
    }
    
    .background-animation {
      .trading-chart {
        background: linear-gradient(180deg, 
          rgba(72, 187, 120, 0.15) 0%,
          rgba(72, 187, 120, 0) 100%);
      }
    }
  }
}

// Animations
@keyframes chartAnimation {
  0% {
    transform: translateX(-5%);
  }
  100% {
    transform: translateX(5%);
  }
}

@keyframes float {
  0%, 100% {
    transform: translateY(0) translateX(0);
  }
  50% {
    transform: translateY(-20px) translateX(10px);
  }
}

// Responsive styles
@media (max-width: 576px) {
  .login-container {
    .login-card-container {
      padding: 15px;
      
      .login-card {
        .login-header {
          .login-logo {
            height: 50px;
          }
          
          .login-title {
            font-size: 20px;
          }
        }
      }
    }
  }
}
</style>
