<template>
  <div class="error-container">
    <div class="error-content">
      <el-result
        icon="error"
        title="404"
        sub-title="抱歉，您访问的页面不存在"
      >
        <template #extra>
          <el-button type="primary" @click="goHome">返回首页</el-button>
          <el-button @click="goBack">返回上一页</el-button>
        </template>
      </el-result>
      
      <div class="error-desc">
        <p>可能的原因：</p>
        <ul>
          <li>URL输入错误</li>
          <li>链接已过期</li>
          <li>页面已被移除</li>
          <li>您没有访问权限</li>
        </ul>
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
</style>
