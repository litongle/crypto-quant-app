<template>
  <div class="dashboard-container">
    <!-- Loading overlay -->
    <div v-if="loading" class="loading-overlay">
      <el-spin class="loading-spinner" />
      <div class="loading-text">加载中...</div>
    </div>

    <!-- Error alert -->
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      description="请检查网络连接或刷新页面重试"
      show-icon
      closable
      @close="error = ''"
      class="error-alert"
    />

    <!-- Dashboard header -->
    <div class="dashboard-header">
      <h2 class="dashboard-title">
        <el-icon><Odometer /></el-icon>
        交易仪表盘
      </h2>
      <div class="dashboard-actions">
        <el-tooltip content="刷新数据" placement="top">
          <el-button
            :icon="Refresh"
            circle
            plain
            :loading="refreshing"
            @click="refreshDashboard"
          />
        </el-tooltip>
        <el-dropdown trigger="click" @command="handleCommand">
          <el-button plain>
            {{ currentTimeRange.label }}
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="range in timeRanges"
                :key="range.value"
                :command="range.value"
              >
                {{ range.label }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- Overview metrics -->
    <div class="metrics-grid">
      <el-card class="metric-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>总收益 (USDT)</span>
            <el-tag
              :type="totalPnl >= 0 ? 'success' : 'danger'"
              size="small"
              effect="dark"
            >
              {{ totalPnl >= 0 ? '盈利' : '亏损' }}
            </el-tag>
          </div>
        </template>
        <div class="metric-value" :class="{ 'profit': totalPnl >= 0, 'loss': totalPnl < 0 }">
          {{ formatCurrency(totalPnl) }}
          <div class="metric-change">
            <el-icon v-if="totalPnl >= 0"><CaretTop /></el-icon>
            <el-icon v-else><CaretBottom /></el-icon>
            {{ formatPercentage(totalPnlPercentage) }}
          </div>
        </div>
      </el-card>

      <el-card class="metric-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>活跃持仓</span>
            <el-tag size="small" effect="plain">{{ activePositions.length }} 个</el-tag>
          </div>
        </template>
        <div class="metric-value">
          {{ activePositions.length }}
          <div class="metric-change">
            <span>总价值: {{ formatCurrency(totalPositionValue) }}</span>
          </div>
        </div>
      </el-card>

      <el-card class="metric-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>今日交易</span>
            <el-tag size="small" effect="plain">{{ todayTrades }} 笔</el-tag>
          </div>
        </template>
        <div class="metric-value">
          {{ todayTrades }}
          <div class="metric-change">
            <span>成功率: {{ formatPercentage(successRate) }}</span>
          </div>
        </div>
      </el-card>

      <el-card class="metric-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>策略状态</span>
            <el-tag
              :type="strategyStatus === 'running' ? 'success' : (strategyStatus === 'paused' ? 'warning' : 'info')"
              size="small"
              effect="dark"
            >
              {{ strategyStatusText }}
            </el-tag>
          </div>
        </template>
        <div class="metric-value strategy-controls">
          <el-button-group>
            <el-button
              :type="strategyStatus === 'running' ? 'success' : 'default'"
              :icon="VideoPlay"
              :disabled="strategyStatus === 'running'"
              @click="startTrading"
            >
              启动
            </el-button>
            <el-button
              :type="strategyStatus === 'paused' ? 'warning' : 'default'"
              :icon="VideoPause"
              :disabled="strategyStatus === 'paused'"
              @click="pauseTrading"
            >
              暂停
            </el-button>
            <el-button
              type="danger"
              :icon="CircleClose"
              @click="emergencyStop"
            >
              紧急停止
            </el-button>
          </el-button-group>
        </div>
      </el-card>
    </div>

    <!-- Main content grid -->
    <div class="dashboard-grid">
      <!-- Price chart section -->
      <el-card class="chart-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>实时价格走势</span>
            <div class="card-header-actions">
              <el-select
                v-model="selectedSymbol"
                size="small"
                placeholder="选择交易对"
                @change="changeSymbol"
              >
                <el-option
                  v-for="symbol in tradingSymbols"
                  :key="symbol.value"
                  :label="symbol.label"
                  :value="symbol.value"
                />
              </el-select>
              <el-select
                v-model="selectedTimeframe"
                size="small"
                placeholder="选择时间周期"
                @change="changeTimeframe"
              >
                <el-option
                  v-for="timeframe in timeframes"
                  :key="timeframe.value"
                  :label="timeframe.label"
                  :value="timeframe.value"
                />
              </el-select>
            </div>
          </div>
        </template>
        <div class="chart-container">
          <div v-if="chartLoading" class="chart-loading">
            <el-spin />
            <span>加载图表数据...</span>
          </div>
          <div v-else-if="chartError" class="chart-error">
            <el-empty :description="chartError" />
            <el-button size="small" @click="loadChartData">重试</el-button>
          </div>
          <div v-else ref="priceChartRef" class="price-chart"></div>
          <div class="chart-info">
            <div class="price-info">
              <div class="current-price" :class="{ 'price-up': priceChange >= 0, 'price-down': priceChange < 0 }">
                {{ formatCurrency(currentPrice) }}
              </div>
              <div class="price-change" :class="{ 'price-up': priceChange >= 0, 'price-down': priceChange < 0 }">
                <el-icon v-if="priceChange >= 0"><CaretTop /></el-icon>
                <el-icon v-else><CaretBottom /></el-icon>
                {{ formatCurrency(priceChange) }} ({{ formatPercentage(priceChangePercentage) }})
              </div>
            </div>
            <div class="chart-indicators">
              <el-tag size="small" effect="plain">RSI: {{ formatNumber(rsiValue) }}</el-tag>
              <el-tag size="small" effect="plain">成交量: {{ formatVolume(volume) }}</el-tag>
              <el-tag size="small" effect="plain">
                <span v-if="signalDirection === 'buy'" class="signal buy">买入信号</span>
                <span v-else-if="signalDirection === 'sell'" class="signal sell">卖出信号</span>
                <span v-else>无信号</span>
              </el-tag>
            </div>
          </div>
        </div>
      </el-card>

      <!-- Account balance card -->
      <el-card class="balance-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>账户余额</span>
            <el-button size="small" plain @click="syncAccounts">
              <el-icon><Refresh /></el-icon>
              同步
            </el-button>
          </div>
        </template>
        <div v-if="accountsLoading" class="loading-container">
          <el-spin />
          <span>加载账户数据...</span>
        </div>
        <el-empty v-else-if="!accounts.length" description="暂无账户数据" />
        <div v-else class="account-list">
          <div v-for="(account, index) in accounts" :key="index" class="account-item">
            <div class="account-info">
              <div class="account-name">{{ account.name }}</div>
              <div class="account-exchange">{{ account.exchange }}</div>
            </div>
            <div class="balance-info">
              <div class="balance-value">{{ formatCurrency(account.balance) }}</div>
              <div class="balance-details">
                <div class="balance-detail">
                  <span>可用:</span>
                  <span>{{ formatCurrency(account.available) }}</span>
                </div>
                <div class="balance-detail">
                  <span>冻结:</span>
                  <span>{{ formatCurrency(account.frozen) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-card>

      <!-- Recent trades table -->
      <el-card class="trades-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>最近交易</span>
            <el-button size="small" plain @click="loadRecentTrades">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </template>
        <div v-if="tradesLoading" class="loading-container">
          <el-spin />
          <span>加载交易数据...</span>
        </div>
        <el-empty v-else-if="!recentTrades.length" description="暂无交易数据" />
        <el-table
          v-else
          :data="recentTrades"
          style="width: 100%"
          size="small"
          max-height="300"
        >
          <el-table-column prop="time" label="时间" width="150">
            <template #default="scope">
              {{ formatDate(scope.row.time) }}
            </template>
          </el-table-column>
          <el-table-column prop="symbol" label="交易对" width="100" />
          <el-table-column prop="type" label="类型" width="80">
            <template #default="scope">
              <el-tag
                :type="scope.row.type === 'buy' ? 'success' : 'danger'"
                size="small"
                effect="plain"
              >
                {{ scope.row.type === 'buy' ? '买入' : '卖出' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="price" label="价格" width="100">
            <template #default="scope">
              {{ formatCurrency(scope.row.price) }}
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="数量" width="100">
            <template #default="scope">
              {{ formatNumber(scope.row.amount) }}
            </template>
          </el-table-column>
          <el-table-column prop="pnl" label="盈亏" width="100">
            <template #default="scope">
              <span :class="{ 'profit': scope.row.pnl >= 0, 'loss': scope.row.pnl < 0 }">
                {{ formatCurrency(scope.row.pnl) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态">
            <template #default="scope">
              <el-tag
                :type="getStatusType(scope.row.status)"
                size="small"
                effect="plain"
              >
                {{ getStatusText(scope.row.status) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- Strategy performance card -->
      <el-card class="performance-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>策略绩效</span>
            <div class="card-header-actions">
              <el-select
                v-model="selectedStrategy"
                size="small"
                placeholder="选择策略"
                @change="changeStrategy"
              >
                <el-option
                  v-for="strategy in strategies"
                  :key="strategy.value"
                  :label="strategy.label"
                  :value="strategy.value"
                />
              </el-select>
            </div>
          </div>
        </template>
        <div v-if="strategyLoading" class="loading-container">
          <el-spin />
          <span>加载策略数据...</span>
        </div>
        <el-empty v-else-if="!strategyPerformance.trades" description="暂无策略数据" />
        <div v-else class="strategy-performance">
          <div class="performance-metrics">
            <div class="performance-metric">
              <div class="metric-label">交易次数</div>
              <div class="metric-data">{{ strategyPerformance.trades }}</div>
            </div>
            <div class="performance-metric">
              <div class="metric-label">胜率</div>
              <div class="metric-data">{{ formatPercentage(strategyPerformance.winRate) }}</div>
            </div>
            <div class="performance-metric">
              <div class="metric-label">盈亏比</div>
              <div class="metric-data">{{ formatNumber(strategyPerformance.profitFactor) }}</div>
            </div>
            <div class="performance-metric">
              <div class="metric-label">最大回撤</div>
              <div class="metric-data">{{ formatPercentage(strategyPerformance.maxDrawdown) }}</div>
            </div>
          </div>
          <div ref="performanceChartRef" class="performance-chart"></div>
        </div>
      </el-card>

      <!-- Active positions card -->
      <el-card class="positions-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>活跃持仓</span>
            <el-button size="small" plain @click="loadPositions">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </template>
        <div v-if="positionsLoading" class="loading-container">
          <el-spin />
          <span>加载持仓数据...</span>
        </div>
        <el-empty v-else-if="!activePositions.length" description="暂无活跃持仓" />
        <el-table
          v-else
          :data="activePositions"
          style="width: 100%"
          size="small"
          max-height="300"
        >
          <el-table-column prop="symbol" label="交易对" width="100" />
          <el-table-column prop="direction" label="方向" width="80">
            <template #default="scope">
              <el-tag
                :type="scope.row.direction === 'long' ? 'success' : 'danger'"
                size="small"
                effect="plain"
              >
                {{ scope.row.direction === 'long' ? '多' : '空' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="entryPrice" label="开仓价" width="100">
            <template #default="scope">
              {{ formatCurrency(scope.row.entryPrice) }}
            </template>
          </el-table-column>
          <el-table-column prop="currentPrice" label="当前价" width="100">
            <template #default="scope">
              {{ formatCurrency(scope.row.currentPrice) }}
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="数量" width="100">
            <template #default="scope">
              {{ formatNumber(scope.row.amount) }}
            </template>
          </el-table-column>
          <el-table-column prop="leverage" label="杠杆" width="80">
            <template #default="scope">
              {{ scope.row.leverage }}x
            </template>
          </el-table-column>
          <el-table-column prop="unrealizedPnl" label="未实现盈亏">
            <template #default="scope">
              <span :class="{ 'profit': scope.row.unrealizedPnl >= 0, 'loss': scope.row.unrealizedPnl < 0 }">
                {{ formatCurrency(scope.row.unrealizedPnl) }}
                ({{ formatPercentage(scope.row.unrealizedPnlPercentage) }})
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150">
            <template #default="scope">
              <el-button
                size="small"
                type="primary"
                plain
                @click="closePosition(scope.row)"
              >
                平仓
              </el-button>
              <el-button
                size="small"
                plain
                @click="editPosition(scope.row)"
              >
                编辑
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- Market overview card -->
      <el-card class="market-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>市场概览</span>
            <el-button size="small" plain @click="loadMarketData">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </template>
        <div v-if="marketLoading" class="loading-container">
          <el-spin />
          <span>加载市场数据...</span>
        </div>
        <el-empty v-else-if="!marketData.length" description="暂无市场数据" />
        <div v-else class="market-overview">
          <el-tabs v-model="marketTab" class="market-tabs">
            <el-tab-pane label="涨幅榜" name="gainers">
              <el-table
                :data="topGainers"
                style="width: 100%"
                size="small"
                max-height="300"
              >
                <el-table-column prop="symbol" label="交易对" width="100" />
                <el-table-column prop="price" label="价格" width="120">
                  <template #default="scope">
                    {{ formatCurrency(scope.row.price) }}
                  </template>
                </el-table-column>
                <el-table-column prop="change" label="涨幅" width="100">
                  <template #default="scope">
                    <span class="price-up">
                      <el-icon><CaretTop /></el-icon>
                      {{ formatPercentage(scope.row.change) }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column prop="volume" label="成交量">
                  <template #default="scope">
                    {{ formatVolume(scope.row.volume) }}
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="100">
                  <template #default="scope">
                    <el-button
                      size="small"
                      type="primary"
                      plain
                      @click="selectSymbol(scope.row.symbol)"
                    >
                      查看
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="跌幅榜" name="losers">
              <el-table
                :data="topLosers"
                style="width: 100%"
                size="small"
                max-height="300"
              >
                <el-table-column prop="symbol" label="交易对" width="100" />
                <el-table-column prop="price" label="价格" width="120">
                  <template #default="scope">
                    {{ formatCurrency(scope.row.price) }}
                  </template>
                </el-table-column>
                <el-table-column prop="change" label="跌幅" width="100">
                  <template #default="scope">
                    <span class="price-down">
                      <el-icon><CaretBottom /></el-icon>
                      {{ formatPercentage(scope.row.change) }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column prop="volume" label="成交量">
                  <template #default="scope">
                    {{ formatVolume(scope.row.volume) }}
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="100">
                  <template #default="scope">
                    <el-button
                      size="small"
                      type="primary"
                      plain
                      @click="selectSymbol(scope.row.symbol)"
                    >
                      查看
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="成交榜" name="volume">
              <el-table
                :data="topVolume"
                style="width: 100%"
                size="small"
                max-height="300"
              >
                <el-table-column prop="symbol" label="交易对" width="100" />
                <el-table-column prop="price" label="价格" width="120">
                  <template #default="scope">
                    {{ formatCurrency(scope.row.price) }}
                  </template>
                </el-table-column>
                <el-table-column prop="change" label="涨跌幅" width="100">
                  <template #default="scope">
                    <span :class="{ 'price-up': scope.row.change >= 0, 'price-down': scope.row.change < 0 }">
                      <el-icon v-if="scope.row.change >= 0"><CaretTop /></el-icon>
                      <el-icon v-else><CaretBottom /></el-icon>
                      {{ formatPercentage(scope.row.change) }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column prop="volume" label="成交量">
                  <template #default="scope">
                    {{ formatVolume(scope.row.volume) }}
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="100">
                  <template #default="scope">
                    <el-button
                      size="small"
                      type="primary"
                      plain
                      @click="selectSymbol(scope.row.symbol)"
                    >
                      查看
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </div>
      </el-card>

      <!-- System status card -->
      <el-card class="system-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>系统状态</span>
            <el-button size="small" plain @click="checkSystemStatus">
              <el-icon><Refresh /></el-icon>
              检查
            </el-button>
          </div>
        </template>
        <div v-if="systemLoading" class="loading-container">
          <el-spin />
          <span>检查系统状态...</span>
        </div>
        <div v-else class="system-status">
          <div class="status-items">
            <div class="status-item">
              <div class="status-label">API 服务</div>
              <div class="status-value">
                <el-tag
                  :type="systemStatus.api ? 'success' : 'danger'"
                  size="small"
                  effect="plain"
                >
                  {{ systemStatus.api ? '正常' : '异常' }}
                </el-tag>
              </div>
            </div>
            <div class="status-item">
              <div class="status-label">数据库</div>
              <div class="status-value">
                <el-tag
                  :type="systemStatus.database ? 'success' : 'danger'"
                  size="small"
                  effect="plain"
                >
                  {{ systemStatus.database ? '正常' : '异常' }}
                </el-tag>
              </div>
            </div>
            <div class="status-item">
              <div class="status-label">Redis</div>
              <div class="status-value">
                <el-tag
                  :type="systemStatus.redis ? 'success' : 'danger'"
                  size="small"
                  effect="plain"
                >
                  {{ systemStatus.redis ? '正常' : '异常' }}
                </el-tag>
              </div>
            </div>
            <div class="status-item">
              <div class="status-label">WebSocket</div>
              <div class="status-value">
                <el-tag
                  :type="systemStatus.websocket ? 'success' : 'danger'"
                  size="small"
                  effect="plain"
                >
                  {{ systemStatus.websocket ? '正常' : '异常' }}
                </el-tag>
              </div>
            </div>
            <div class="status-item">
              <div class="status-label">交易所API</div>
              <div class="status-value">
                <el-tag
                  :type="systemStatus.exchange ? 'success' : 'danger'"
                  size="small"
                  effect="plain"
                >
                  {{ systemStatus.exchange ? '正常' : '异常' }}
                </el-tag>
              </div>
            </div>
            <div class="status-item">
              <div class="status-label">任务调度</div>
              <div class="status-value">
                <el-tag
                  :type="systemStatus.tasks ? 'success' : 'danger'"
                  size="small"
                  effect="plain"
                >
                  {{ systemStatus.tasks ? '正常' : '异常' }}
                </el-tag>
              </div>
            </div>
          </div>
          <div class="system-resources">
            <div class="resource-title">系统资源</div>
            <div class="resource-item">
              <div class="resource-label">CPU 使用率</div>
              <el-progress
                :percentage="systemResources.cpu"
                :color="getResourceColor(systemResources.cpu)"
                :stroke-width="10"
                :show-text="true"
              />
            </div>
            <div class="resource-item">
              <div class="resource-label">内存使用率</div>
              <el-progress
                :percentage="systemResources.memory"
                :color="getResourceColor(systemResources.memory)"
                :stroke-width="10"
                :show-text="true"
              />
            </div>
            <div class="resource-item">
              <div class="resource-label">磁盘使用率</div>
              <el-progress
                :percentage="systemResources.disk"
                :color="getResourceColor(systemResources.disk)"
                :stroke-width="10"
                :show-text="true"
              />
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <!-- Position edit dialog -->
    <el-dialog
      v-model="positionDialogVisible"
      title="编辑持仓"
      width="500px"
      destroy-on-close
    >
      <el-form
        v-if="currentPosition"
        ref="positionFormRef"
        :model="positionForm"
        label-width="120px"
      >
        <el-form-item label="交易对">
          <el-input v-model="currentPosition.symbol" disabled />
        </el-form-item>
        <el-form-item label="方向">
          <el-tag
            :type="currentPosition.direction === 'long' ? 'success' : 'danger'"
            effect="plain"
          >
            {{ currentPosition.direction === 'long' ? '多' : '空' }}
          </el-tag>
        </el-form-item>
        <el-form-item label="开仓价格">
          <el-input v-model="currentPosition.entryPrice" disabled />
        </el-form-item>
        <el-form-item label="当前价格">
          <el-input v-model="currentPosition.currentPrice" disabled />
        </el-form-item>
        <el-form-item label="止损价格">
          <el-input-number
            v-model="positionForm.stopLoss"
            :min="0"
            :precision="2"
            :step="1"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="止盈价格">
          <el-input-number
            v-model="positionForm.takeProfit"
            :min="0"
            :precision="2"
            :step="1"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="positionDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="savePosition">保存</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Emergency stop confirmation dialog -->
    <el-dialog
      v-model="emergencyDialogVisible"
      title="紧急停止"
      width="400px"
    >
      <div class="emergency-warning">
        <el-icon class="warning-icon"><WarningFilled /></el-icon>
        <p>紧急停止将立即关闭所有交易并平仓所有持仓，确定要执行此操作吗？</p>
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="emergencyDialogVisible = false">取消</el-button>
          <el-button type="danger" @click="confirmEmergencyStop">确认停止</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import { format, parseISO } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import {
  Odometer, Refresh, ArrowDown, CaretTop, CaretBottom,
  VideoPlay, VideoPause, CircleClose, WarningFilled
} from '@element-plus/icons-vue'
import {
  getDashboardData,
  getChartData,
  getAccountBalances,
  getRecentTrades,
  getActivePositions,
  getStrategyPerformance,
  getMarketOverview,
  getSystemStatus,
  updatePosition,
  closePosition as apiClosePosition,
  startStrategy,
  pauseStrategy,
  emergencyStopTrading
} from '@/api/trading'

// WebSocket connection
const { connect, disconnect, connected, lastMessage } = useWebSocket()

// Dashboard state
const loading = ref(false)
const refreshing = ref(false)
const error = ref('')

// Chart references
const priceChartRef = ref<HTMLElement | null>(null)
const performanceChartRef = ref<HTMLElement | null>(null)
let priceChart: echarts.ECharts | null = null
let performanceChart: echarts.ECharts | null = null

// Time range selection
const timeRanges = [
  { label: '今日', value: 'today' },
  { label: '7天', value: '7d' },
  { label: '30天', value: '30d' },
  { label: '全部', value: 'all' }
]
const currentTimeRange = ref(timeRanges[0])

// Trading symbols
const tradingSymbols = [
  { label: 'ETH/USDT', value: 'ETH-USDT' },
  { label: 'BTC/USDT', value: 'BTC-USDT' },
  { label: 'SOL/USDT', value: 'SOL-USDT' },
  { label: 'BNB/USDT', value: 'BNB-USDT' },
  { label: 'XRP/USDT', value: 'XRP-USDT' }
]
const selectedSymbol = ref('ETH-USDT')

// Timeframes
const timeframes = [
  { label: '1分钟', value: '1m' },
  { label: '5分钟', value: '5m' },
  { label: '15分钟', value: '15m' },
  { label: '1小时', value: '1h' },
  { label: '4小时', value: '4h' },
  { label: '1天', value: '1d' }
]
const selectedTimeframe = ref('15m')

// Strategy selection
const strategies = [
  { label: 'RSI分层策略', value: 'rsi_layered' },
  { label: 'MACD策略', value: 'macd' },
  { label: '布林带策略', value: 'bollinger' }
]
const selectedStrategy = ref('rsi_layered')

// Market tab
const marketTab = ref('gainers')

// Dashboard data
const totalPnl = ref(0)
const totalPnlPercentage = ref(0)
const todayTrades = ref(0)
const successRate = ref(0)
const strategyStatus = ref('paused')
const totalPositionValue = ref(0)

// Chart data
const chartLoading = ref(false)
const chartError = ref('')
const currentPrice = ref(0)
const priceChange = ref(0)
const priceChangePercentage = ref(0)
const rsiValue = ref(0)
const volume = ref(0)
const signalDirection = ref('')

// Account data
const accountsLoading = ref(false)
const accounts = ref<any[]>([])

// Trades data
const tradesLoading = ref(false)
const recentTrades = ref<any[]>([])

// Positions data
const positionsLoading = ref(false)
const activePositions = ref<any[]>([])
const positionDialogVisible = ref(false)
const currentPosition = ref<any>(null)
const positionForm = reactive({
  stopLoss: 0,
  takeProfit: 0
})

// Strategy data
const strategyLoading = ref(false)
const strategyPerformance = reactive({
  trades: 0,
  winRate: 0,
  profitFactor: 0,
  maxDrawdown: 0,
  equityCurve: [] as any[]
})

// Market data
const marketLoading = ref(false)
const marketData = ref<any[]>([])
const topGainers = computed(() => {
  return marketData.value
    .filter(item => item.change > 0)
    .sort((a, b) => b.change - a.change)
    .slice(0, 10)
})
const topLosers = computed(() => {
  return marketData.value
    .filter(item => item.change < 0)
    .sort((a, b) => a.change - b.change)
    .slice(0, 10)
})
const topVolume = computed(() => {
  return [...marketData.value]
    .sort((a, b) => b.volume - a.volume)
    .slice(0, 10)
})

// System status
const systemLoading = ref(false)
const systemStatus = reactive({
  api: true,
  database: true,
  redis: true,
  websocket: true,
  exchange: true,
  tasks: true
})
const systemResources = reactive({
  cpu: 0,
  memory: 0,
  disk: 0
})

// Emergency stop
const emergencyDialogVisible = ref(false)

// Computed properties
const strategyStatusText = computed(() => {
  switch (strategyStatus.value) {
    case 'running': return '运行中'
    case 'paused': return '已暂停'
    case 'stopped': return '已停止'
    default: return '未知'
  }
})

// Methods
// Format utilities
const formatCurrency = (value: number) => {
  if (isNaN(value)) return '0.00'
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

const formatPercentage = (value: number) => {
  if (isNaN(value)) return '0.00%'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

const formatNumber = (value: number) => {
  if (isNaN(value)) return '0'
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6
  })
}

const formatVolume = (value: number) => {
  if (isNaN(value)) return '0'
  if (value >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(2)}B`
  } else if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`
  } else if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)}K`
  }
  return value.toFixed(2)
}

const formatDate = (dateStr: string) => {
  try {
    const date = typeof dateStr === 'string' ? parseISO(dateStr) : new Date(dateStr)
    return format(date, 'yyyy-MM-dd HH:mm:ss', { locale: zhCN })
  } catch (e) {
    return dateStr
  }
}

const getStatusType = (status: string) => {
  switch (status) {
    case 'completed': return 'success'
    case 'pending': return 'warning'
    case 'failed': return 'danger'
    default: return 'info'
  }
}

const getStatusText = (status: string) => {
  switch (status) {
    case 'completed': return '已完成'
    case 'pending': return '处理中'
    case 'failed': return '失败'
    default: return status
  }
}

const getResourceColor = (percentage: number) => {
  if (percentage < 60) return '#67c23a'
  if (percentage < 80) return '#e6a23c'
  return '#f56c6c'
}

// Dashboard actions
const refreshDashboard = async () => {
  if (refreshing.value) return
  
  refreshing.value = true
  try {
    await Promise.all([
      loadDashboardData(),
      loadChartData(),
      loadPositions(),
      loadRecentTrades(),
      changeStrategy(),
      loadMarketData(),
      checkSystemStatus()
    ])
    
    ElMessage.success('数据已刷新')
  } catch (err) {
    console.error('刷新仪表盘失败:', err)
    error.value = '刷新数据失败，请重试'
  } finally {
    refreshing.value = false
  }
}

const handleCommand = (command: string) => {
  const range = timeRanges.find(r => r.value === command)
  if (range) {
    currentTimeRange.value = range
    loadDashboardData()
  }
}

// Data loading functions
const loadDashboardData = async () => {
  try {
    loading.value = true
    error.value = ''
    
    const { data } = await getDashboardData(currentTimeRange.value.value)
    
    totalPnl.value = data.totalPnl || 0
    totalPnlPercentage.value = data.totalPnlPercentage || 0
    todayTrades.value = data.todayTrades || 0
    successRate.value = data.successRate || 0
    strategyStatus.value = data.strategyStatus || 'paused'
    totalPositionValue.value = data.totalPositionValue || 0
    
    // Load accounts
    await syncAccounts()
  } catch (err) {
    console.error('加载仪表盘数据失败:', err)
    error.value = '加载仪表盘数据失败，请重试'
  } finally {
    loading.value = false
  }
}

const loadChartData = async () => {
  try {
    chartLoading.value = true
    chartError.value = ''
    
    const { data } = await getChartData(selectedSymbol.value, selectedTimeframe.value)
    
    currentPrice.value = data.currentPrice || 0
    priceChange.value = data.priceChange || 0
    priceChangePercentage.value = data.priceChangePercentage || 0
    rsiValue.value = data.rsiValue || 0
    volume.value = data.volume || 0
    signalDirection.value = data.signalDirection || ''
    
    // Initialize chart after data is loaded
    await nextTick()
    initPriceChart(data.klines)
  } catch (err) {
    console.error('加载图表数据失败:', err)
    chartError.value = '加载图表数据失败，请重试'
  } finally {
    chartLoading.value = false
  }
}

const syncAccounts = async () => {
  try {
    accountsLoading.value = true
    
    const { data } = await getAccountBalances()
    accounts.value = data || []
  } catch (err) {
    console.error('加载账户数据失败:', err)
    ElMessage.error('加载账户数据失败')
  } finally {
    accountsLoading.value = false
  }
}

const loadRecentTrades = async () => {
  try {
    tradesLoading.value = true
    
    const { data } = await getRecentTrades()
    recentTrades.value = data || []
  } catch (err) {
    console.error('加载交易数据失败:', err)
    ElMessage.error('加载交易数据失败')
  } finally {
    tradesLoading.value = false
  }
}

const loadPositions = async () => {
  try {
    positionsLoading.value = true
    
    const { data } = await getActivePositions()
    activePositions.value = data || []
    
    // Calculate total position value
    totalPositionValue.value = activePositions.value.reduce((sum, pos) => {
      return sum + (pos.amount * pos.currentPrice)
    }, 0)
  } catch (err) {
    console.error('加载持仓数据失败:', err)
    ElMessage.error('加载持仓数据失败')
  } finally {
    positionsLoading.value = false
  }
}

const changeStrategy = async () => {
  try {
    strategyLoading.value = true
    
    const { data } = await getStrategyPerformance(selectedStrategy.value, currentTimeRange.value.value)
    
    strategyPerformance.trades = data.trades || 0
    strategyPerformance.winRate = data.winRate || 0
    strategyPerformance.profitFactor = data.profitFactor || 0
    strategyPerformance.maxDrawdown = data.maxDrawdown || 0
    strategyPerformance.equityCurve = data.equityCurve || []
    
    // Initialize performance chart after data is loaded
    await nextTick()
    initPerformanceChart(data.equityCurve)
  } catch (err) {
    console.error('加载策略数据失败:', err)
    ElMessage.error('加载策略数据失败')
  } finally {
    strategyLoading.value = false
  }
}

const loadMarketData = async () => {
  try {
    marketLoading.value = true
    
    const { data } = await getMarketOverview()
    marketData.value = data || []
  } catch (err) {
    console.error('加载市场数据失败:', err)
    ElMessage.error('加载市场数据失败')
  } finally {
    marketLoading.value = false
  }
}

const checkSystemStatus = async () => {
  try {
    systemLoading.value = true
    
    const { data } = await getSystemStatus()
    
    systemStatus.api = data.api || false
    systemStatus.database = data.database || false
    systemStatus.redis = data.redis || false
    systemStatus.websocket = data.websocket || false
    systemStatus.exchange = data.exchange || false
    systemStatus.tasks = data.tasks || false
    
    systemResources.cpu = data.resources?.cpu || 0
    systemResources.memory = data.resources?.memory || 0
    systemResources.disk = data.resources?.disk || 0
  } catch (err) {
    console.error('检查系统状态失败:', err)
    ElMessage.error('检查系统状态失败')
  } finally {
    systemLoading.value = false
  }
}

// Chart functions
const initPriceChart = (klineData: any[]) => {
  if (!priceChartRef.value) return
  
  // Dispose existing chart instance if it exists
  if (priceChart) {
    priceChart.dispose()
  }
  
  // Create new chart instance
  priceChart = echarts.init(priceChartRef.value)
  
  // Prepare data
  const dates = klineData.map(item => item[0])
  const values = klineData.map(item => [item[1], item[2], item[3], item[4]]) // Open, High, Low, Close
  const volumes = klineData.map(item => item[5])
  
  // Chart options
  const option = {
    animation: false,
    legend: {
      data: ['K线', '成交量'],
      top: 10,
      left: 'center'
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross'
      },
      borderWidth: 1,
      borderColor: '#ccc',
      padding: 10,
      textStyle: {
        color: '#000'
      },
      formatter: function (params: any[]) {
        const candleStick = params[0]
        const date = candleStick.axisValue
        const data = candleStick.data
        
        return `
          <div style="font-size: 14px; color: #666; font-weight: bold">${date}</div>
          <div style="margin-top: 5px;">
            <div>开: ${data[0]}</div>
            <div>高: ${data[1]}</div>
            <div>低: ${data[2]}</div>
            <div>收: ${data[3]}</div>
            <div>量: ${formatVolume(volumes[candleStick.dataIndex])}</div>
          </div>
        `
      }
    },
    axisPointer: {
      link: [{ xAxisIndex: 'all' }]
    },
    grid: [
      {
        left: '10%',
        right: '10%',
        height: '60%'
      },
      {
        left: '10%',
        right: '10%',
        top: '75%',
        height: '15%'
      }
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        scale: true,
        boundaryGap: false,
        axisLine: { onZero: false },
        splitLine: { show: false },
        splitNumber: 20,
        min: 'dataMin',
        max: 'dataMax',
        axisPointer: {
          z: 100
        }
      },
      {
        type: 'category',
        gridIndex: 1,
        data: dates,
        scale: true,
        boundaryGap: false,
        axisLine: { onZero: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        splitNumber: 20,
        min: 'dataMin',
        max: 'dataMax'
      }
    ],
    yAxis: [
      {
        scale: true,
        splitArea: {
          show: true
        }
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false }
      }
    ],
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0, 1],
        start: 50,
        end: 100
      },
      {
        show: true,
        xAxisIndex: [0, 1],
        type: 'slider',
        top: '92%',
        start: 50,
        end: 100
      }
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: values,
        itemStyle: {
          color: '#ef5350',
          color0: '#26a69a',
          borderColor: '#ef5350',
          borderColor0: '#26a69a'
        }
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes,
        itemStyle: {
          color: function(params: any) {
            const i = params.dataIndex
            return values[i][0] <= values[i][3] ? '#26a69a' : '#ef5350'
          }
        }
      }
    ]
  }
  
  // Set chart options
  priceChart.setOption(option)
  
  // Handle resize
  window.addEventListener('resize', () => {
    priceChart?.resize()
  })
}

const initPerformanceChart = (equityCurve: any[]) => {
  if (!performanceChartRef.value) return
  
  // Dispose existing chart instance if it exists
  if (performanceChart) {
    performanceChart.dispose()
  }
  
  // Create new chart instance
  performanceChart = echarts.init(performanceChartRef.value)
  
  // Prepare data
  const dates = equityCurve.map(item => item.date)
  const equity = equityCurve.map(item => item.equity)
  const benchmark = equityCurve.map(item => item.benchmark)
  
  // Chart options
  const option = {
    tooltip: {
      trigger: 'axis',
      formatter: function(params: any[]) {
        const date = params[0].axisValue
        let html = `<div style="font-size: 14px; color: #666; font-weight: bold">${date}</div>`
        
        params.forEach(param => {
          const color = param.color
          const seriesName = param.seriesName
          const value = param.value
          html += `<div style="margin-top: 5px;">
            <span style="display:inline-block;margin-right:5px;border-radius:10px;width:10px;height:10px;background-color:${color};"></span>
            ${seriesName}: ${formatCurrency(value)}
          </div>`
        })
        
        return html
      }
    },
    legend: {
      data: ['策略收益', '基准收益'],
      top: 10,
      left: 'center'
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter: '{value}'
      }
    },
    series: [
      {
        name: '策略收益',
        type: 'line',
        data: equity,
        smooth: true,
        showSymbol: false,
        lineStyle: {
          width: 3,
          color: '#409EFF'
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(64, 158, 255, 0.5)' },
            { offset: 1, color: 'rgba(64, 158, 255, 0.1)' }
          ])
        }
      },
      {
        name: '基准收益',
        type: 'line',
        data: benchmark,
        smooth: true,
        showSymbol: false,
        lineStyle: {
          width: 2,
          type: 'dashed',
          color: '#909399'
        }
      }
    ]
  }
  
  // Set chart options
  performanceChart.setOption(option)
  
  // Handle resize
  window.addEventListener('resize', () => {
    performanceChart?.resize()
  })
}

// Action handlers
const changeSymbol = () => {
  loadChartData()
}

const changeTimeframe = () => {
  loadChartData()
}

const selectSymbol = (symbol: string) => {
  selectedSymbol.value = symbol
  loadChartData()
}

const startTrading = async () => {
  try {
    await startStrategy(selectedStrategy.value)
    strategyStatus.value = 'running'
    ElMessage.success('交易已启动')
  } catch (err) {
    console.error('启动交易失败:', err)
    ElMessage.error('启动交易失败')
  }
}

const pauseTrading = async () => {
  try {
    await pauseStrategy(selectedStrategy.value)
    strategyStatus.value = 'paused'
    ElMessage.success('交易已暂停')
  } catch (err) {
    console.error('暂停交易失败:', err)
    ElMessage.error('暂停交易失败')
  }
}

const emergencyStop = () => {
  emergencyDialogVisible.value = true
}

const confirmEmergencyStop = async () => {
  try {
    await emergencyStopTrading()
    strategyStatus.value = 'stopped'
    ElMessage.success('紧急停止已执行，所有交易已关闭')
    emergencyDialogVisible.value = false
    
    // Reload positions after emergency stop
    await loadPositions()
  } catch (err) {
    console.error('紧急停止失败:', err)
    ElMessage.error('紧急停止失败')
  }
}

const editPosition = (position: any) => {
  currentPosition.value = position
  positionForm.stopLoss = position.stopLoss || 0
  positionForm.takeProfit = position.takeProfit || 0
  positionDialogVisible.value = true
}

const savePosition = async () => {
  if (!currentPosition.value) return
  
  try {
    await updatePosition(currentPosition.value.id, positionForm)
    ElMessage.success('持仓更新成功')
    positionDialogVisible.value = false
    
    // Reload positions after update
    await loadPositions()
  } catch (err) {
    console.error('更新持仓失败:', err)
    ElMessage.error('更新持仓失败')
  }
}

const closePosition = async (position: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要平仓 ${position.symbol} ${position.direction === 'long' ? '多' : '空'}单吗？`,
      '确认平仓',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await apiClosePosition(position.id)
    ElMessage.success('平仓请求已发送')
    
    // Reload positions after close
    await loadPositions()
  } catch (err) {
    if (err !== 'cancel') {
      console.error('平仓失败:', err)
      ElMessage.error('平仓失败')
    }
  }
}

// WebSocket message handler
const handleWebSocketMessage = (message: string) => {
  try {
    const data = JSON.parse(message)
    
    // Handle different message types
    switch (data.type) {
      case 'price_update':
        // Update price data
        if (data.symbol === selectedSymbol.value) {
          currentPrice.value = data.price
          priceChange.value = data.change
          priceChangePercentage.value = data.changePercentage
        }
        break
        
      case 'trade_executed':
        // Add new trade to recent trades
        ElMessage.info(`${data.symbol} ${data.side === 'buy' ? '买入' : '卖出'}订单已执行`)
        loadRecentTrades()
        break
        
      case 'position_update':
        // Update positions
        loadPositions()
        break
        
      case 'account_update':
        // Update account balances
        syncAccounts()
        break
        
      case 'strategy_signal':
        // Update strategy signal
        if (data.symbol === selectedSymbol.value) {
          signalDirection.value = data.direction
          ElMessage.info(`${data.symbol} 产生${data.direction === 'buy' ? '买入' : '卖出'}信号`)
        }
        break
        
      case 'system_status':
        // Update system status
        systemStatus.api = data.api
        systemStatus.database = data.database
        systemStatus.redis = data.redis
        systemStatus.websocket = data.websocket
        systemStatus.exchange = data.exchange
        systemStatus.tasks = data.tasks
        
        if (data.resources) {
          systemResources.cpu = data.resources.cpu
          systemResources.memory = data.resources.memory
          systemResources.disk = data.resources.disk
        }
        break
    }
  } catch (err) {
    console.error('处理WebSocket消息失败:', err)
  }
}

// Lifecycle hooks
onMounted(async () => {
  // Connect to WebSocket
  connect('/api/ws/dashboard')
  
  // Load initial data
  await loadDashboardData()
  await loadChartData()
  await loadPositions()
  await loadRecentTrades()
  await changeStrategy()
  await loadMarketData()
  await checkSystemStatus()
})

onBeforeUnmount(() => {
  // Disconnect WebSocket
  disconnect()
  
  // Dispose chart instances
  if (priceChart) {
    priceChart.dispose()
    priceChart = null
  }
  
  if (performanceChart) {
    performanceChart.dispose()
    performanceChart = null
  }
})

// Watch for WebSocket messages
watch(lastMessage, (newMessage) => {
  if (newMessage) {
    handleWebSocketMessage(newMessage)
  }
})
</script>

<style lang="scss" scoped>
.dashboard-container {
  position: relative;
  padding: 16px;
  
  // Loading overlay
  .loading-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(255, 255, 255, 0.8);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    z-index: 1000;
    
    .loading-spinner {
      font-size: 32px;
    }
    
    .loading-text {
      margin-top: 16px;
      font-size: 16px;
      color: var(--el-text-color-secondary);
    }
  }
  
  // Error alert
  .error-alert {
    margin-bottom: 16px;
  }
  
  // Dashboard header
  .dashboard-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    
    .dashboard-title {
      margin: 0;
      font-size: 24px;
      font-weight: 600;
      display: flex;
      align-items: center;
      
      .el-icon {
        margin-right: 8px;
        font-size: 24px;
      }
    }
    
    .dashboard-actions {
      display: flex;
      gap: 10px;
    }
  }
  
  // Metrics grid
  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 20px;
    
    .metric-card {
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      
      .metric-value {
        font-size: 28px;
        font-weight: 600;
        margin-top: 10px;
        
        &.profit {
          color: var(--el-color-success);
        }
        
        &.loss {
          color: var(--el-color-danger);
        }
        
        .metric-change {
          font-size: 14px;
          font-weight: normal;
          margin-top: 5px;
          display: flex;
          align-items: center;
          
          .el-icon {
            margin-right: 4px;
          }
        }
      }
      
      .strategy-controls {
        font-size: 16px;
        display: flex;
        justify-content: center;
      }
    }
  }
  
  // Main dashboard grid
  .dashboard-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    grid-template-rows: auto auto;
    gap: 16px;
    
    .chart-card {
      grid-column: 1 / 3;
      grid-row: 1 / 2;
      
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        
        .card-header-actions {
          display: flex;
          gap: 10px;
        }
      }
      
      .chart-container {
        position: relative;
        height: 400px;
        
        .chart-loading,
        .chart-error {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
        }
        
        .price-chart {
          height: 350px;
          width: 100%;
        }
        
        .chart-info {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 10px;
          
          .price-info {
            .current-price {
              font-size: 20px;
              font-weight: 600;
              
              &.price-up {
                color: var(--el-color-success);
              }
              
              &.price-down {
                color: var(--el-color-danger);
              }
            }
            
            .price-change {
              display: flex;
              align-items: center;
              font-size: 14px;
              
              &.price-up {
                color: var(--el-color-success);
              }
              
              &.price-down {
                color: var(--el-color-danger);
              }
              
              .el-icon {
                margin-right: 4px;
              }
            }
          }
          
          .chart-indicators {
            display: flex;
            gap: 10px;
            
            .signal {
              &.buy {
                color: var(--el-color-success);
              }
              
              &.sell {
                color: var(--el-color-danger);
              }
            }
          }
        }
      }
    }
    
    .balance-card {
      grid-column: 3 / 4;
      grid-row: 1 / 2;
      
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      
      .loading-container {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        height: 200px;
      }
      
      .account-list {
        max-height: 400px;
        overflow-y: auto;
        
        .account-item {
          display: flex;
          justify-content: space-between;
          padding: 12px 0;
          border-bottom: 1px solid var(--el-border-color-lighter);
          
          &:last-child {
            border-bottom: none;
          }
          
          .account-info {
            .account-name {
              font-weight: 600;
              margin-bottom: 4px;
            }
            
            .account-exchange {
              font-size: 12px;
              color: var(--el-text-color-secondary);
            }
          }
          
          .balance-info {
            text-align: right;
            
            .balance-value {
              font-weight: 600;
              font-size: 16px;
              margin-bottom: 4px;
            }
            
            .balance-details {
              font-size: 12px;
              color: var(--el-text-color-secondary);
              
              .balance-detail {
                display: flex;
                justify-content: space-between;
                gap: 10px;
              }
            }
          }
        }
      }
    }
    
    .trades-card {
      grid-column: 1 / 3;
      grid-row: 2 / 3;
      
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      
      .loading-container {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        height: 200px;
      }
    }
    
    .performance-card {
      grid-column: 3 / 4;
      grid-row: 2 / 3;
      
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        
        .card-header-actions {
          display: flex;
          gap: 10px;
        }
      }
      
      .loading-container {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        height: 200px;
      }
      
      .strategy-performance {
        .performance-metrics {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 10px;
          margin-bottom: 15px;
          
          .performance-metric {
            text-align: center;
            
            .metric-label {
              font-size: 12px;
              color: var(--el-text-color-secondary);
              margin-bottom: 5px;
            }
            
            .metric-data {
              font-size: 16px;
              font-weight: 600;
            }
          }
        }
        
        .performance-chart {
          height: 200px;
          width: 100%;
        }
      }
    }
    
    .positions-card {
      grid-column: 1 / 3;
      grid-row: 3 / 4;
      
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      
      .loading-container {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        height: 200px;
      }
    }
    
    .market-card {
      grid-column: 3 / 4;
      grid-row: 3 / 4;
      
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      
      .loading-container {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        height: 200px;
      }
      
      .market-overview {
        .market-tabs {
          height: 100%;
        }
      }
    }
    
    .system-card {
      grid-column: 1 / 4;
      grid-row: 4 / 5;
      
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      
      .loading-container {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        height: 100px;
      }
      
      .system-status {
        display: flex;
        
        .status-items {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 16px;
          flex: 1;
          
          .status-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            border-radius: 4px;
            background-color: var(--el-fill-color-light);
            
            .status-label {
              font-weight: 500;
            }
          }
        }
        
        .system-resources {
          width: 300px;
          margin-left: 20px;
          
          .resource-title {
            font-weight: 600;
            margin-bottom: 10px;
          }
          
          .resource-item {
            margin-bottom: 15px;
            
            .resource-label {
              margin-bottom: 5px;
              font-size: 14px;
            }
          }
        }
      }
    }
  }
  
  // Common styles
  .profit {
    color: var(--el-color-success);
  }
  
  .loss {
    color: var(--el-color-danger);
  }
  
  .price-up {
    color: var(--el-color-success);
  }
  
  .price-down {
    color: var(--el-color-danger);
  }
  
  // Emergency dialog
  .emergency-warning {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    
    .warning-icon {
      font-size: 48px;
      color: var(--el-color-danger);
      margin-bottom: 16px;
    }
    
    p {
      font-size: 16px;
      line-height: 1.5;
    }
  }
}

// Responsive styles
@media (max-width: 1200px) {
  .dashboard-container {
    .metrics-grid {
      grid-template-columns: repeat(2, 1fr);
    }
    
    .dashboard-grid {
      grid-template-columns: 1fr;
      
      .chart-card {
        grid-column: 1;
        grid-row: auto;
      }
      
      .balance-card {
        grid-column: 1;
        grid-row: auto;
      }
      
      .trades-card {
        grid-column: 1;
        grid-row: auto;
      }
      
      .performance-card {
        grid-column: 1;
        grid-row: auto;
      }
      
      .positions-card {
        grid-column: 1;
        grid-row: auto;
      }
      
      .market-card {
        grid-column: 1;
        grid-row: auto;
      }
      
      .system-card {
        grid-column: 1;
        grid-row: auto;
        
        .system-status {
          flex-direction: column;
          
          .system-resources {
            width: 100%;
            margin-left: 0;
            margin-top: 20px;
          }
        }
      }
    }
  }
}

@media (max-width: 768px) {
  .dashboard-container {
    .metrics-grid {
      grid-template-columns: 1fr;
    }
    
    .dashboard-grid {
      .system-card {
        .system-status {
          .status-items {
            grid-template-columns: 1fr;
          }
        }
      }
    }
  }
}

// Dark mode adaptations
:deep(.dark-mode) {
  .dashboard-container {
    .loading-overlay {
      background-color: rgba(0, 0, 0, 0.7);
    }
    
    .system-status {
      .status-items {
        .status-item {
          background-color: #1e