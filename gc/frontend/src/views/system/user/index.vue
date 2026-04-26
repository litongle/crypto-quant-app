<template>
  <div class="app-container">
    <el-card class="box-card">
      <template #header>
        <div class="card-header">
          <span>用户管理</span>
          <el-button type="primary" @click="handleAddUser" v-if="hasPermission('user:add')">
            <el-icon><Plus /></el-icon>添加用户
          </el-button>
        </div>
      </template>

      <!-- 搜索过滤区 -->
      <el-form :model="queryParams" ref="queryForm" :inline="true" class="search-form">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="queryParams.username" placeholder="请输入用户名" clearable />
        </el-form-item>
        <el-form-item label="姓名" prop="realName">
          <el-input v-model="queryParams.realName" placeholder="请输入姓名" clearable />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-select v-model="queryParams.status" placeholder="用户状态" clearable>
            <el-option label="启用" value="enabled" />
            <el-option label="禁用" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色" prop="roleId">
          <el-select v-model="queryParams.roleId" placeholder="用户角色" clearable>
            <el-option label="管理员" value="admin" />
            <el-option label="交易员" value="trader" />
            <el-option label="查看者" value="viewer" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleQuery">
            <el-icon><Search /></el-icon>搜索
          </el-button>
          <el-button @click="resetQuery">
            <el-icon><Refresh /></el-icon>重置
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 数据表格 -->
      <el-table
        v-loading="loading"
        :data="userList"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" width="120" />
        <el-table-column prop="realName" label="姓名" width="120" />
        <el-table-column prop="email" label="邮箱" width="180" />
        <el-table-column prop="phone" label="手机号" width="120" />
        <el-table-column prop="roleName" label="角色" width="100" />
        <el-table-column prop="status" label="状态" width="80">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'enabled' ? 'success' : 'danger'">
              {{ scope.row.status === 'enabled' ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="lastLoginTime" label="最后登录时间" width="160" />
        <el-table-column prop="createTime" label="创建时间" width="160" />
        <el-table-column label="操作" fixed="right" width="200">
          <template #default="scope">
            <el-button 
              type="primary" 
              link
              @click="handleEditUser(scope.row)"
              v-if="hasPermission('user:edit')"
            >
              编辑
            </el-button>
            <el-button 
              type="primary" 
              link
              @click="handleResetPassword(scope.row)"
              v-if="hasPermission('user:reset')"
            >
              重置密码
            </el-button>
            <el-button 
              type="danger" 
              link
              @click="handleDeleteUser(scope.row)"
              v-if="hasPermission('user:delete')"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="queryParams.pageNum"
          v-model:page-size="queryParams.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 用户表单对话框 -->
    <el-dialog
      :title="dialogTitle"
      v-model="dialogVisible"
      width="600px"
      append-to-body
    >
      <el-form
        ref="userFormRef"
        :model="userForm"
        :rules="userFormRules"
        label-width="100px"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="userForm.username" placeholder="请输入用户名" :disabled="userForm.id !== ''" />
        </el-form-item>
        <el-form-item label="姓名" prop="realName">
          <el-input v-model="userForm.realName" placeholder="请输入姓名" />
        </el-form-item>
        <el-form-item label="密码" prop="password" v-if="userForm.id === ''">
          <el-input v-model="userForm.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword" v-if="userForm.id === ''">
          <el-input v-model="userForm.confirmPassword" type="password" placeholder="请确认密码" show-password />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="userForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="userForm.phone" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item label="角色" prop="roleId">
          <el-select v-model="userForm.roleId" placeholder="请选择角色">
            <el-option label="管理员" value="admin" />
            <el-option label="交易员" value="trader" />
            <el-option label="查看者" value="viewer" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="userForm.status">
            <el-radio label="enabled">启用</el-radio>
            <el-radio label="disabled">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input v-model="userForm.remark" type="textarea" placeholder="请输入备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitForm">确定</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Refresh } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'

// 权限判断
const hasPermission = (permission: string): boolean => {
  // 这里应该从用户权限中判断，暂时返回true作为示例
  return true
}

// 查询参数
const queryParams = reactive({
  pageNum: 1,
  pageSize: 10,
  username: '',
  realName: '',
  status: '',
  roleId: ''
})

// 表格数据
const loading = ref(false)
const userList = ref<any[]>([])
const total = ref(0)

// 表单相关
const dialogVisible = ref(false)
const dialogTitle = ref('')
const userFormRef = ref<FormInstance>()
const userForm = reactive({
  id: '',
  username: '',
  realName: '',
  password: '',
  confirmPassword: '',
  email: '',
  phone: '',
  roleId: '',
  status: 'enabled',
  remark: ''
})

// 表单校验规则
const userFormRules = reactive<FormRules>({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度在 3 到 20 个字符', trigger: 'blur' }
  ],
  realName: [
    { required: true, message: '请输入姓名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于 6 个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== userForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱地址', trigger: 'blur' }
  ],
  roleId: [
    { required: true, message: '请选择角色', trigger: 'change' }
  ]
})

// 生命周期钩子
onMounted(() => {
  getList()
})

// 获取用户列表
const getList = () => {
  loading.value = true
  // 这里应该调用API获取用户列表，暂时使用模拟数据
  setTimeout(() => {
    userList.value = [
      {
        id: '1',
        username: 'admin',
        realName: '系统管理员',
        email: 'admin@example.com',
        phone: '13800138000',
        roleId: 'admin',
        roleName: '管理员',
        status: 'enabled',
        lastLoginTime: '2025-07-13 10:30:45',
        createTime: '2025-06-01 08:00:00'
      },
      {
        id: '2',
        username: 'trader1',
        realName: '交易员1',
        email: 'trader1@example.com',
        phone: '13800138001',
        roleId: 'trader',
        roleName: '交易员',
        status: 'enabled',
        lastLoginTime: '2025-07-12 16:20:33',
        createTime: '2025-06-05 09:15:00'
      },
      {
        id: '3',
        username: 'viewer1',
        realName: '查看者1',
        email: 'viewer1@example.com',
        phone: '13800138002',
        roleId: 'viewer',
        roleName: '查看者',
        status: 'disabled',
        lastLoginTime: '2025-07-10 11:45:22',
        createTime: '2025-06-10 14:30:00'
      }
    ]
    total.value = 3
    loading.value = false
  }, 500)
}

// 搜索
const handleQuery = () => {
  queryParams.pageNum = 1
  getList()
}

// 重置
const resetQuery = () => {
  queryParams.username = ''
  queryParams.realName = ''
  queryParams.status = ''
  queryParams.roleId = ''
  handleQuery()
}

// 分页处理
const handleSizeChange = (val: number) => {
  queryParams.pageSize = val
  getList()
}

const handleCurrentChange = (val: number) => {
  queryParams.pageNum = val
  getList()
}

// 添加用户
const handleAddUser = () => {
  resetForm()
  dialogTitle.value = '添加用户'
  dialogVisible.value = true
}

// 编辑用户
const handleEditUser = (row: any) => {
  resetForm()
  dialogTitle.value = '编辑用户'
  // 填充表单数据
  Object.assign(userForm, {
    id: row.id,
    username: row.username,
    realName: row.realName,
    email: row.email,
    phone: row.phone,
    roleId: row.roleId,
    status: row.status,
    remark: row.remark || ''
  })
  dialogVisible.value = true
}

// 重置密码
const handleResetPassword = (row: any) => {
  ElMessageBox.prompt('请输入新密码', '重置密码', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputType: 'password',
    inputValidator: (value) => {
      return value.length >= 6 ? true : '密码长度不能少于6个字符'
    }
  }).then(({ value }) => {
    // 这里应该调用API重置密码
    ElMessage.success(`用户 ${row.username} 的密码已重置`)
  }).catch(() => {
    // 取消操作
  })
}

// 删除用户
const handleDeleteUser = (row: any) => {
  ElMessageBox.confirm(
    `确认删除用户 ${row.username} 吗？`,
    '警告',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(() => {
    // 这里应该调用API删除用户
    ElMessage.success(`用户 ${row.username} 已删除`)
    getList()
  }).catch(() => {
    // 取消操作
  })
}

// 重置表单
const resetForm = () => {
  userForm.id = ''
  userForm.username = ''
  userForm.realName = ''
  userForm.password = ''
  userForm.confirmPassword = ''
  userForm.email = ''
  userForm.phone = ''
  userForm.roleId = ''
  userForm.status = 'enabled'
  userForm.remark = ''
  
  // 重置表单验证
  if (userFormRef.value) {
    userFormRef.value.resetFields()
  }
}

// 提交表单
const submitForm = async () => {
  if (!userFormRef.value) return
  
  await userFormRef.value.validate((valid) => {
    if (valid) {
      // 这里应该调用API保存用户
      const isEdit = userForm.id !== ''
      const message = isEdit ? `用户 ${userForm.username} 已更新` : `用户 ${userForm.username} 已创建`
      
      ElMessage.success(message)
      dialogVisible.value = false
      getList()
    }
  })
}
</script>

<style scoped>
.app-container {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.search-form {
  margin-bottom: 20px;
}

.pagination-container {
  margin-top: 20px;
  text-align: right;
}
</style>
