<template>
  <div class="app-container">
    <el-card class="box-card">
      <template #header>
        <div class="card-header">
          <span>角色管理</span>
          <el-button type="primary" @click="handleAddRole" v-if="hasPermission('role:add')">
            <el-icon><Plus /></el-icon>添加角色
          </el-button>
        </div>
      </template>

      <!-- 搜索过滤区 -->
      <el-form :model="queryParams" ref="queryForm" :inline="true" class="search-form">
        <el-form-item label="角色名称" prop="roleName">
          <el-input v-model="queryParams.roleName" placeholder="请输入角色名称" clearable />
        </el-form-item>
        <el-form-item label="角色编码" prop="roleCode">
          <el-input v-model="queryParams.roleCode" placeholder="请输入角色编码" clearable />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-select v-model="queryParams.status" placeholder="角色状态" clearable>
            <el-option label="启用" value="enabled" />
            <el-option label="禁用" value="disabled" />
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
        :data="roleList"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="roleName" label="角色名称" width="150" />
        <el-table-column prop="roleCode" label="角色编码" width="150" />
        <el-table-column prop="description" label="描述" />
        <el-table-column prop="status" label="状态" width="80">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'enabled' ? 'success' : 'danger'">
              {{ scope.row.status === 'enabled' ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="createTime" label="创建时间" width="160" />
        <el-table-column label="操作" fixed="right" width="250">
          <template #default="scope">
            <el-button 
              type="primary" 
              link
              @click="handleEditRole(scope.row)"
              v-if="hasPermission('role:edit')"
            >
              编辑
            </el-button>
            <el-button 
              type="primary" 
              link
              @click="handlePermission(scope.row)"
              v-if="hasPermission('role:permission')"
            >
              分配权限
            </el-button>
            <el-button 
              type="danger" 
              link
              @click="handleDeleteRole(scope.row)"
              v-if="hasPermission('role:delete')"
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

    <!-- 角色表单对话框 -->
    <el-dialog
      :title="dialogTitle"
      v-model="dialogVisible"
      width="600px"
      append-to-body
    >
      <el-form
        ref="roleFormRef"
        :model="roleForm"
        :rules="roleFormRules"
        label-width="100px"
      >
        <el-form-item label="角色名称" prop="roleName">
          <el-input v-model="roleForm.roleName" placeholder="请输入角色名称" />
        </el-form-item>
        <el-form-item label="角色编码" prop="roleCode">
          <el-input v-model="roleForm.roleCode" placeholder="请输入角色编码" />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="roleForm.status">
            <el-radio label="enabled">启用</el-radio>
            <el-radio label="disabled">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="排序" prop="sort">
          <el-input-number v-model="roleForm.sort" :min="0" :max="999" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="roleForm.description" type="textarea" placeholder="请输入描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitForm">确定</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 权限分配对话框 -->
    <el-dialog
      title="分配权限"
      v-model="permissionDialogVisible"
      width="600px"
      append-to-body
    >
      <div v-if="currentRole">
        <p class="permission-role-info">
          角色: <el-tag>{{ currentRole.roleName }}</el-tag>
        </p>
        <el-tree
          ref="permissionTreeRef"
          :data="permissionTree"
          show-checkbox
          node-key="id"
          :props="{ label: 'name' }"
          :default-checked-keys="checkedPermissions"
        />
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="permissionDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="savePermissions">保存</el-button>
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
  roleName: '',
  roleCode: '',
  status: ''
})

// 表格数据
const loading = ref(false)
const roleList = ref<any[]>([])
const total = ref(0)

// 表单相关
const dialogVisible = ref(false)
const dialogTitle = ref('')
const roleFormRef = ref<FormInstance>()
const roleForm = reactive({
  id: '',
  roleName: '',
  roleCode: '',
  status: 'enabled',
  sort: 0,
  description: ''
})

// 表单校验规则
const roleFormRules = reactive<FormRules>({
  roleName: [
    { required: true, message: '请输入角色名称', trigger: 'blur' },
    { min: 2, max: 50, message: '角色名称长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  roleCode: [
    { required: true, message: '请输入角色编码', trigger: 'blur' },
    { min: 2, max: 50, message: '角色编码长度在 2 到 50 个字符', trigger: 'blur' }
  ]
})

// 权限相关
const permissionDialogVisible = ref(false)
const currentRole = ref<any>(null)
const permissionTree = ref<any[]>([])
const checkedPermissions = ref<string[]>([])
const permissionTreeRef = ref()

// 生命周期钩子
onMounted(() => {
  getList()
})

// 获取角色列表
const getList = () => {
  loading.value = true
  // 这里应该调用API获取角色列表，暂时使用模拟数据
  setTimeout(() => {
    roleList.value = [
      {
        id: '1',
        roleName: '超级管理员',
        roleCode: 'admin',
        description: '系统最高权限，可以操作所有功能',
        status: 'enabled',
        sort: 0,
        createTime: '2025-06-01 08:00:00'
      },
      {
        id: '2',
        roleName: '交易员',
        roleCode: 'trader',
        description: '负责交易策略的执行和监控',
        status: 'enabled',
        sort: 1,
        createTime: '2025-06-05 09:15:00'
      },
      {
        id: '3',
        roleName: '查看者',
        roleCode: 'viewer',
        description: '只能查看数据，无操作权限',
        status: 'enabled',
        sort: 2,
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
  queryParams.roleName = ''
  queryParams.roleCode = ''
  queryParams.status = ''
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

// 添加角色
const handleAddRole = () => {
  resetForm()
  dialogTitle.value = '添加角色'
  dialogVisible.value = true
}

// 编辑角色
const handleEditRole = (row: any) => {
  resetForm()
  dialogTitle.value = '编辑角色'
  // 填充表单数据
  Object.assign(roleForm, {
    id: row.id,
    roleName: row.roleName,
    roleCode: row.roleCode,
    status: row.status,
    sort: row.sort || 0,
    description: row.description || ''
  })
  dialogVisible.value = true
}

// 删除角色
const handleDeleteRole = (row: any) => {
  ElMessageBox.confirm(
    `确认删除角色 ${row.roleName} 吗？`,
    '警告',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(() => {
    // 这里应该调用API删除角色
    ElMessage.success(`角色 ${row.roleName} 已删除`)
    getList()
  }).catch(() => {
    // 取消操作
  })
}

// 分配权限
const handlePermission = (row: any) => {
  currentRole.value = row
  // 这里应该调用API获取权限树和已分配的权限，暂时使用模拟数据
  permissionTree.value = [
    {
      id: '1',
      name: '系统管理',
      children: [
        { id: '1-1', name: '用户管理' },
        { id: '1-2', name: '角色管理' },
        { id: '1-3', name: '菜单管理' },
        { id: '1-4', name: '部门管理' }
      ]
    },
    {
      id: '2',
      name: '交易管理',
      children: [
        { id: '2-1', name: '持仓管理' },
        { id: '2-2', name: '订单管理' },
        { id: '2-3', name: '交易历史' }
      ]
    },
    {
      id: '3',
      name: '策略管理',
      children: [
        { id: '3-1', name: '策略列表' },
        { id: '3-2', name: '策略创建' },
        { id: '3-3', name: '策略回测' }
      ]
    }
  ]
  
  // 模拟已分配的权限
  if (row.roleCode === 'admin') {
    checkedPermissions.value = ['1', '2', '3']
  } else if (row.roleCode === 'trader') {
    checkedPermissions.value = ['2', '3']
  } else {
    checkedPermissions.value = []
  }
  
  permissionDialogVisible.value = true
}

// 保存权限
const savePermissions = () => {
  if (!permissionTreeRef.value) return
  
  const checkedKeys = permissionTreeRef.value.getCheckedKeys()
  const halfCheckedKeys = permissionTreeRef.value.getHalfCheckedKeys()
  const allCheckedKeys = [...checkedKeys, ...halfCheckedKeys]
  
  // 这里应该调用API保存权限
  ElMessage.success(`角色 ${currentRole.value.roleName} 的权限已更新`)
  permissionDialogVisible.value = false
}

// 重置表单
const resetForm = () => {
  roleForm.id = ''
  roleForm.roleName = ''
  roleForm.roleCode = ''
  roleForm.status = 'enabled'
  roleForm.sort = 0
  roleForm.description = ''
  
  // 重置表单验证
  if (roleFormRef.value) {
    roleFormRef.value.resetFields()
  }
}

// 提交表单
const submitForm = async () => {
  if (!roleFormRef.value) return
  
  await roleFormRef.value.validate((valid) => {
    if (valid) {
      // 这里应该调用API保存角色
      const isEdit = roleForm.id !== ''
      const message = isEdit ? `角色 ${roleForm.roleName} 已更新` : `角色 ${roleForm.roleName} 已创建`
      
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

.permission-role-info {
  margin-bottom: 15px;
  font-size: 14px;
}
</style>
