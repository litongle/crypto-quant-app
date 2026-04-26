<template>
  <div class="app-container">
    <el-card class="box-card">
      <template #header>
        <div class="card-header">
          <span>系统配置</span>
          <el-button type="primary" @click="handleSaveConfig" v-if="hasPermission('config:update')">
            <el-icon><Check /></el-icon>保存配置
          </el-button>
        </div>
      </template>

      <el-tabs v-model="activeTab" type="card">
        <!-- 基础配置 -->
        <el-tab-pane label="基础配置" name="basic">
          <el-form :model="basicConfig" label-width="180px" :disabled="!hasPermission('config:update')">
            <el-form-item label="系统名称">
              <el-input v-model="basicConfig.systemName" placeholder="系统名称" />
            </el-form-item>
            <el-form-item label="系统版本">
              <el-input v-model="basicConfig.version" placeholder="系统版本" disabled />
            </el-form-item>
            <el-form-item label="管理员邮箱">
              <el-input v-model="basicConfig.adminEmail" placeholder="管理员邮箱" />
            </el-form-item>
            <el-form-item label="系统公告">
              <el-input v-model="basicConfig.announcement" type="textarea" rows="3" placeholder="系统公告" />
            </el-form-item>
            <el-form-item label="是否启用维护模式">
              <el-switch v-model="basicConfig.maintenanceMode" />
            </el-form-item>
            <el-form-item label="维护模式消息" v-if="basicConfig.maintenanceMode">
              <el-input v-model="basicConfig.maintenanceMessage" type="textarea" rows="2" placeholder="维护模式消息" />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 交易配置 -->
        <el-tab-pane label="交易配置" name="trading">
          <el-form :model="tradingConfig" label-width="180px" :disabled="!hasPermission('config:update')">
            <el-form-item label="默认交易对">
              <el-input v-model="tradingConfig.defaultSymbol" placeholder="默认交易对" />
            </el-form-item>
            <el-form-item label="默认杠杆倍数">
              <el-input-number v-model="tradingConfig.defaultLeverage" :min="1" :max="125" />
            </el-form-item>
            <el-form-item label="默认下单比例">
              <el-slider v-model="tradingConfig.orderRatio" :min="0" :max="100" :format-tooltip="formatPercentage" />
            </el-form-item>
            <el-form-item label="最大持仓比例">
              <el-slider v-model="tradingConfig.maxPositionRatio" :min="0" :max="100" :format-tooltip="formatPercentage" />
            </el-form-item>
            <el-form-item label="自动追加保证金">
              <el-switch v-model="tradingConfig.autoAddMargin" />
            </el-form-item>
            <el-form-item label="交易确认">
              <el-switch v-model="tradingConfig.confirmTrading" />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 数据配置 -->
        <el-tab-pane label="数据配置" name="data">
          <el-form :model="dataConfig" label-width="180px" :disabled="!hasPermission('config:update')">
            <el-form-item label="K线数据保留天数">
              <el-input-number v-model="dataConfig.klineRetentionDays" :min="1" :max="365" />
            </el-form-item>
            <el-form-item label="交易日志保留天数">
              <el-input-number v-model="dataConfig.tradeLogRetentionDays" :min="1" :max="365" />
            </el-form-item>
            <el-form-item label="系统日志保留天数">
              <el-input-number v-model="dataConfig.systemLogRetentionDays" :min="1" :max="365" />
            </el-form-item>
            <el-form-item label="数据备份频率">
              <el-select v-model="dataConfig.backupFrequency">
                <el-option label="每天" value="daily" />
                <el-option label="每周" value="weekly" />
                <el-option label="每月" value="monthly" />
              </el-select>
            </el-form-item>
            <el-form-item label="备份保留数量">
              <el-input-number v-model="dataConfig.backupRetentionCount" :min="1" :max="100" />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 通知配置 -->
        <el-tab-pane label="通知配置" name="notification">
          <el-form :model="notificationConfig" label-width="180px" :disabled="!hasPermission('config:update')">
            <el-form-item label="启用邮件通知">
              <el-switch v-model="notificationConfig.enableEmailNotification" />
            </el-form-item>
            <el-form-item label="启用短信通知">
              <el-switch v-model="notificationConfig.enableSmsNotification" />
            </el-form-item>
            <el-form-item label="启用WebHook通知">
              <el-switch v-model="notificationConfig.enableWebhookNotification" />
            </el-form-item>
            <el-form-item label="WebHook地址" v-if="notificationConfig.enableWebhookNotification">
              <el-input v-model="notificationConfig.webhookUrl" placeholder="WebHook地址" />
            </el-form-item>
            <el-form-item label="通知事件">
              <el-checkbox-group v-model="notificationConfig.notificationEvents">
                <el-checkbox label="order_placed">订单创建</el-checkbox>
                <el-checkbox label="order_filled">订单成交</el-checkbox>
                <el-checkbox label="position_opened">开仓</el-checkbox>
                <el-checkbox label="position_closed">平仓</el-checkbox>
                <el-checkbox label="stop_loss_triggered">止损触发</el-checkbox>
                <el-checkbox label="take_profit_triggered">止盈触发</el-checkbox>
                <el-checkbox label="system_error">系统错误</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 界面配置 -->
        <el-tab-pane label="界面配置" name="ui">
          <el-form :model="uiConfig" label-width="180px" :disabled="!hasPermission('config:update')">
            <el-form-item label="默认主题">
              <el-select v-model="uiConfig.theme">
                <el-option label="浅色" value="light" />
                <el-option label="深色" value="dark" />
                <el-option label="跟随系统" value="auto" />
              </el-select>
            </el-form-item>
            <el-form-item label="表格每页行数">
              <el-select v-model="uiConfig.tablePageSize">
                <el-option label="10" :value="10" />
                <el-option label="20" :value="20" />
                <el-option label="50" :value="50" />
                <el-option label="100" :value="100" />
              </el-select>
            </el-form-item>
            <el-form-item label="显示欢迎页">
              <el-switch v-model="uiConfig.showWelcomePage" />
            </el-form-item>
            <el-form-item label="启用动画效果">
              <el-switch v-model="uiConfig.enableAnimations" />
            </el-form-item>
            <el-form-item label="自动刷新间隔(秒)">
              <el-input-number v-model="uiConfig.autoRefreshInterval" :min="0" :max="300" />
              <span class="form-help-text">0表示不自动刷新</span>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Check } from '@element-plus/icons-vue'

// 权限判断
const hasPermission = (permission: string): boolean => {
  // 这里应该从用户权限中判断，暂时返回true作为示例
  return true
}

// 当前激活的标签页
const activeTab = ref('basic')

// 基础配置
const basicConfig = reactive({
  systemName: 'RSI分层极值追踪量化交易系统',
  version: 'v0.1.0',
  adminEmail: 'admin@example.com',
  announcement: '欢迎使用RSI分层极值追踪量化交易系统，本系统目前处于测试阶段。',
  maintenanceMode: false,
  maintenanceMessage: '系统正在维护中，请稍后再试。'
})

// 交易配置
const tradingConfig = reactive({
  defaultSymbol: 'ETH-USDT-SWAP',
  defaultLeverage: 20,
  orderRatio: 25,
  maxPositionRatio: 80,
  autoAddMargin: false,
  confirmTrading: true
})

// 数据配置
const dataConfig = reactive({
  klineRetentionDays: 7,
  tradeLogRetentionDays: 30,
  systemLogRetentionDays: 90,
  backupFrequency: 'daily',
  backupRetentionCount: 30
})

// 通知配置
const notificationConfig = reactive({
  enableEmailNotification: true,
  enableSmsNotification: false,
  enableWebhookNotification: false,
  webhookUrl: '',
  notificationEvents: ['order_filled', 'position_opened', 'position_closed', 'system_error']
})

// 界面配置
const uiConfig = reactive({
  theme: 'light',
  tablePageSize: 20,
  showWelcomePage: true,
  enableAnimations: true,
  autoRefreshInterval: 30
})

// 格式化百分比
const formatPercentage = (val: number) => {
  return `${val}%`
}

// 生命周期钩子
onMounted(() => {
  loadConfig()
})

// 加载配置
const loadConfig = () => {
  // 这里应该调用API获取系统配置，暂时使用模拟数据
  // 实际应用中应该从后端加载配置
  console.log('加载系统配置')
}

// 保存配置
const handleSaveConfig = () => {
  // 这里应该调用API保存系统配置
  // 实际应用中应该将配置提交到后端
  ElMessage.success('系统配置已保存')
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

.form-help-text {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}

:deep(.el-tabs__header) {
  margin-bottom: 20px;
}

:deep(.el-form-item) {
  max-width: 600px;
}
</style>
