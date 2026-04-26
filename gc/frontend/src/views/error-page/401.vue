<template>
  <div class="error-container">
    <div class="error-content">
      <el-result
        icon="warning"
        title="401"
        sub-title="抱歉，您没有权限访问此页面"
      >
        <template #extra>
          <el-button type="primary" @click="goHome">返回首页</el-button>
          <el-button @click="goBack">返回上一页</el-button>
        </template>
      </el-result>
      
      <div class="error-desc">
        <p>可能的原因：</p>
        <ul>
          <li>您的账户没有所需的访问权限</li>
          <li>您的登录会话已过期</li>
          <li>您需要更高级别的权限</li>
          <li>系统管理员限制了此功能的访问</li>
        </ul>
        <p class="contact-info">如需帮助，请联系系统管理员</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

// 返回首页
const goHome = () => {
  router.push('/')
}

// 返回上一页
const goBack = () => {
  router.go(-1)
}
</script>

<style scoped>
.error-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  min-height: 80vh;
  background-color: #f5f7fa;
  padding: 20px;
}

.error-content {
  max-width: 600px;
  width: 100%;
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  padding: 20px;
}

.error-desc {
  margin-top: 30px;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
  color: #606266;
}

.error-desc ul {
  padding-left: 20px;
  margin-top: 10px;
  color: #909399;
}

.contact-info {
  margin-top: 15px;
  font-weight: 500;
  color: #409eff;
}
</style>
