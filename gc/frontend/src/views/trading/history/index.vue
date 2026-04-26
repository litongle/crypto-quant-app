<template>
  <div class="history-container">
    <!-- Page header with title and actions -->
    <div class="page-header">
      <div class="header-title">
        <el-icon><Histogram /></el-icon>
        <h2>交易历史</h2>
      </div>
      <div class="header-actions">
        <el-button-group>
          <el-button
            type="primary"
            :icon="Refresh"
            :loading="loading"
            @click="refreshHistory"
          >
            刷新
          </el-button>
          <el-dropdown trigger="click" @command="handleExport">
            <el-button :icon="Download">
              导出
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="excel">导出到Excel</el-dropdown-item>
                <el-dropdown-item command="csv">导出到CSV</el-dropdown-item>
                <el-dropdown-item command="json">导出到JSON</el-dropdown-item>
                <el-dropdown-item command="pdf">导出到PDF</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </el-button-group>
      </div>
    </div>

    <!-- Filters section -->
    <el-card class="filter-card" shadow="never">
      <div class="filter-container">
        <el-form :inline="true" :model="filterForm" @submit.prevent>
          <el-form-item label="时间范围">
            <el-date-picker
              v-model="filterForm.dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
              @change="handleFilterChange"
            />
          </el-form-item>
          
          <el-form-item label="交易对">
            <el-select
              v-model="filterForm.symbol"
              placeholder="选择交易对"
              clearable
              filterable
              @change="handleFilterChange"
            >
              <el-option
                v-for="item in symbolOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          
          <el-form-item label="方向">
            <el-select
              v-model="filterForm.direction"
              placeholder="选择方向"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="多" value="long" />
              <el-option label="空" value="short" />
            </el-select>
          </el-form-item>
          
          <el-form-item label="策略">
            <el-select
              v-model="filterForm.strategy"
              placeholder="选择策略"
              clearable
              @change="handleFilterChange"
            >
              <el-option
                v-for="item in strategyOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          
          <el-form-item label="盈亏">
            <el-select
              v-model="filterForm.pnlStatus"
              placeholder="盈亏状态"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="盈利" value="profit" />
              <el-option label="亏损" value="loss" />
            </el-select>
          </el-form-item>
          
          <el-form-item>
            <el-button type="primary" @click="handleFilterChange">筛选</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </el-form-item>
        </el-form>
        
        <!-- Advanced search toggle -->
        <div class="advanced-search-toggle" @click="toggleAdvancedSearch">
          <span>高级筛选</span>
          <el-icon>
            <component :is="advancedSearchVisible ? 'ArrowUp' : 'ArrowDown'" />
          </el-icon>
        </div>
      </div>
      
      <!-- Advanced search options -->
      <div v-show="advancedSearchVisible" class="advanced-search">
        <el-form :inline="true" :model="advancedFilterForm" @submit.prevent>
          <el-form-item label="持仓时间">
            <el-select
              v-model="advancedFilterForm.holdingTime"
              placeholder="持仓时间"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="< 1小时" value="lt_1h" />
              <el-option label="1-24小时" value="1h_24h" />
              <el-option label="1-7天" value="1d_7d" />
              <el-option label="> 7天" value="gt_7d" />
            </el-select>
          </el-form-item>
          
          <el-form-item label="杠杆范围">
            <el-slider
              v-model="advancedFilterForm.leverageRange"
              range
              :min="1"
              :max="125"
              :marks="{1: '1x', 25: '25x', 50: '50x', 75: '75x', 100: '100x', 125: '125x'}"
              @change="handleFilterChange"
            />
          </el-form-item>
          
          <el-form-item label="盈亏范围 (%)">
            <el-slider
              v-model="advancedFilterForm.pnlRange"
              range
              :min="-100"
              :max="100"
              :marks="{'-100': '-100%', '-50': '-50%', 0: '0%', 50: '50%', 100: '100%'}"
              @change="handleFilterChange"
            />
          </el-form-item>
          
          <el-form-item label="账户">
            <el-select
              v-model="advancedFilterForm.account"
              placeholder="选择账户"
              clearable
              @change="handleFilterChange"
            >
              <el-option
                v-for="item in accountOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          
          <el-form-item label="平仓原因">
            <el-select
              v-model="advancedFilterForm.closeReason"
              placeholder="平仓原因"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="手动平仓" value="manual" />
              <el-option label="止盈触发" value="take_profit" />
              <el-option label="止损触发" value="stop_loss" />
              <el-option label="强制平仓" value="liquidation" />
              <el-option label="策略信号" value="strategy" />
              <el-option label="系统平仓" value="system" />
            </el-select>
          </el-form-item>
        </el-form>
      </div>
    </el-card>

    <!-- Statistics cards -->
    <div class="statistics-cards">
      <el-row :gutter="16">
        <el-col :xs="24" :sm="12" :md="6">
          <el-card shadow="hover" class="statistic-card">
            <div class="statistic-title">总交易次数</div>
            <div class="statistic-value">{{ totalTrades }}</div>
            <div class="statistic-footer">
              <span>多: {{ longTrades }}</span>
              <span>空: {{ shortTrades }}</span>
            </div>
          </el-card>
        </el-col>
        
        <el-col :xs="24" :sm="12" :md="6">
          <el-card shadow="hover" class="statistic-card">
            <div class="statistic-title">总盈亏</div>
            <div 
              class="statistic-value" 
              :class="{ 'profit': totalPnl > 0, 'loss': totalPnl < 0 }"
            >
              {{ formatCurrency(totalPnl) }}
            </div>
            <div class="statistic-footer">
              <span>{{ formatPercentage(totalPnlPercentage) }}</span>
            </div>
          </el-card>
        </el-col>
        
        <el-col :xs="24" :sm="12" :md="6">
          <el-card shadow="hover" class="statistic-card">
            <div class="statistic-title">胜率</div>
            <div class="statistic-value">{{ formatPercentage(winRate) }}</div>
            <div class="statistic-footer">
              <el-progress
                :percentage="winRate"
                :stroke-width="8"
                :format="() => ''"
                :color="winRateColor"
              />
            </div>
          </el-card>
        </el-col>
        
        <el-col :xs="24" :sm="12" :md="6">
          <el-card shadow="hover" class="statistic-card">
            <div class="statistic-title">盈亏比</div>
            <div class="statistic-value">{{ profitLossRatio.toFixed(2) }}</div>
            <div class="statistic-footer">
              <span>平均盈利: {{ formatCurrency(avgProfit) }}</span>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- Trading history table -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>交易历史</span>
            <el-tag type="info" size="small">{{ filteredHistory.length }}</el-tag>
          </div>
          <div class="header-right">
            <el-input
              v-model="searchKeyword"
              placeholder="搜索交易..."
              prefix-icon="Search"
              clearable
              @input="handleSearch"
            />
            <el-tooltip content="表格设置" placement="top">
              <el-button :icon="Setting" circle @click="showTableSettings = true" />
            </el-tooltip>
            <el-radio-group v-model="timeRange" size="small" @change="handleTimeRangeChange">
              <el-radio-button label="7d">7天</el-radio-button>
              <el-radio-button label="30d">30天</el-radio-button>
              <el-radio-button label="90d">90天</el-radio-button>
              <el-radio-button label="all">全部</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </template>
      
      <!-- Table loading state -->
      <div v-if="loading" class="loading-container">
        <el-spin class="loading-spinner" />
        <span>加载交易数据...</span>
      </div>
      
      <!-- Empty state -->
      <el-empty
        v-else-if="filteredHistory.length === 0"
        description="暂无交易历史"
      >
        <template #image>
          <el-icon class="empty-icon"><Document /></el-icon>
        </template>
        <el-button type="primary" @click="refreshHistory">刷新数据</el-button>
      </el-empty>
      
      <!-- Trading history table -->
      <el-table
        v-else
        ref="historyTableRef"
        :data="paginatedHistory"
        style="width: 100%"
        border
        stripe
        highlight-current-row
        @selection-change="handleSelectionChange"
        @sort-change="handleSortChange"
        @row-click="handleRowClick"
      >
        <el-table-column type="selection" width="55" fixed="left" />
        <el-table-column type="expand">
          <template #default="props">
            <div class="trade-detail">
              <el-descriptions :column="3" border>
                <el-descriptions-item label="交易ID">{{ props.row.id }}</el-descriptions-item>
                <el-descriptions-item label="开仓时间">
                  {{ formatDateTime(props.row.openTime) }}
                </el-descriptions-item>
                <el-descriptions-item label="平仓时间">
                  {{ formatDateTime(props.row.closeTime) }}
                </el-descriptions-item>
                <el-descriptions-item label="持仓时间">
                  {{ props.row.holdingTime }}
                </el-descriptions-item>
                <el-descriptions-item label="账户">
                  {{ props.row.accountName }}
                </el-descriptions-item>
                <el-descriptions-item label="策略">
                  {{ props.row.strategyName || '手动' }}
                </el-descriptions-item>
                <el-descriptions-item label="杠杆">
                  {{ props.row.leverage }}x
                </el-descriptions-item>
                <el-descriptions-item label="保证金">
                  {{ formatCurrency(props.row.margin) }}
                </el-descriptions-item>
                <el-descriptions-item label="资金费率">
                  {{ formatPercentage(props.row.fundingRate || 0) }}
                </el-descriptions-item>
                <el-descriptions-item label="资金费用">
                  {{ formatCurrency(props.row.fundingFee || 0) }}
                </el-descriptions-item>
                <el-descriptions-item label="交易手续费">
                  {{ formatCurrency(props.row.fee || 0) }}
                </el-descriptions-item>
                <el-descriptions-item label="平仓原因">
                  {{ getCloseReasonText(props.row.closeReason) }}
                </el-descriptions-item>
              </el-descriptions>
              
              <div class="trade-charts">
                <div class="chart-container">
                  <h3>价格走势</h3>
                  <div ref="priceChartRef" :id="`price-chart-${props.row.id}`" class="price-chart"></div>
                </div>
              </div>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="symbol" label="交易对" width="120" sortable>
          <template #default="scope">
            <div class="symbol-cell">
              <crypto-icon :symbol="getCryptoSymbol(scope.row.symbol)" class="crypto-icon" />
              <span>{{ scope.row.symbol }}</span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="direction" label="方向" width="80">
          <template #default="scope">
            <el-tag
              :type="scope.row.direction === 'long' ? 'success' : 'danger'"
              effect="plain"
            >
              {{ scope.row.direction === 'long' ? '多' : '空' }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="entryPrice" label="开仓价" width="120" sortable>
          <template #default="scope">
            {{ formatCurrency(scope.row.entryPrice) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="exitPrice" label="平仓价" width="120" sortable>
          <template #default="scope">
            {{ formatCurrency(scope.row.exitPrice) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="amount" label="数量" width="120" sortable>
          <template #default="scope">
            {{ formatNumber(scope.row.amount) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="leverage" label="杠杆" width="80" sortable>
          <template #default="scope">
            <el-tag type="info">{{ scope.row.leverage }}x</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="realizedPnl" label="已实现盈亏" width="150" sortable>
          <template #default="scope">
            <div 
              class="pnl-cell" 
              :class="{
                'profit': scope.row.realizedPnl > 0,
                'loss': scope.row.realizedPnl < 0
              }"
            >
              {{ formatCurrency(scope.row.realizedPnl) }}
              <span class="pnl-percentage">
                ({{ formatPercentage(scope.row.realizedPnlPercentage) }})
              </span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="holdingTime" label="持仓时间" width="120">
          <template #default="scope">
            {{ scope.row.holdingTime }}
          </template>
        </el-table-column>
        
        <el-table-column prop="closeReason" label="平仓原因" width="120">
          <template #default="scope">
            <el-tag size="small" effect="plain">
              {{ getCloseReasonText(scope.row.closeReason) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="closeTime" label="平仓时间" width="160" sortable>
          <template #default="scope">
            {{ formatDateTime(scope.row.closeTime) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" fixed="right" width="100">
          <template #default="scope">
            <el-button-group>
              <el-tooltip content="查看详情" placement="top">
                <el-button 
                  type="info" 
                  :icon="View" 
                  circle
                  @click.stop="viewTradeDetail(scope.row)"
                />
              </el-tooltip>
              <el-tooltip content="再次交易" placement="top">
                <el-button 
                  type="success" 
                  :icon="RefreshRight" 
                  circle
                  @click.stop="repeatTrade(scope.row)"
                />
              </el-tooltip>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- Pagination -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="filteredHistory.length"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- P&L Analysis -->
    <el-card shadow="never" class="pnl-analysis-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>盈亏分析</span>
          </div>
          <div class="header-right">
            <el-radio-group v-model="pnlTimeRange" size="small" @change="updatePnlCharts">
              <el-radio-button label="7d">7天</el-radio-button>
              <el-radio-button label="30d">30天</el-radio-button>
              <el-radio-button label="90d">90天</el-radio-button>
              <el-radio-button label="all">全部</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </template>
      
      <div v-if="pnlLoading" class="loading-container">
        <el-spin class="loading-spinner" />
        <span>加载盈亏数据...</span>
      </div>
      
      <div v-else class="pnl-charts-container">
        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>累计盈亏</h3>
              <div ref="cumulativePnlChartRef" class="pnl-chart"></div>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>每日盈亏</h3>
              <div ref="dailyPnlChartRef" class="pnl-chart"></div>
            </div>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>盈亏分布</h3>
              <div ref="pnlDistributionChartRef" class="pnl-chart"></div>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>回撤分析</h3>
              <div ref="drawdownChartRef" class="pnl-chart"></div>
            </div>
          </el-col>
        </el-row>
      </div>
    </el-card>

    <!-- Performance Metrics -->
    <el-card shadow="never" class="performance-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>绩效指标</span>
          </div>
        </div>
      </template>
      
      <div class="performance-metrics">
        <el-row :gutter="20">
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">总收益率</div>
              <div class="metric-value" :class="{ 'profit': totalReturn > 0, 'loss': totalReturn < 0 }">
                {{ formatPercentage(totalReturn) }}
              </div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">年化收益率</div>
              <div class="metric-value" :class="{ 'profit': annualizedReturn > 0, 'loss': annualizedReturn < 0 }">
                {{ formatPercentage(annualizedReturn) }}
              </div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">夏普比率</div>
              <div class="metric-value">{{ sharpeRatio.toFixed(2) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">最大回撤</div>
              <div class="metric-value loss">{{ formatPercentage(maxDrawdown) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">卡尔马比率</div>
              <div class="metric-value">{{ calmarRatio.toFixed(2) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">索提诺比率</div>
              <div class="metric-value">{{ sortinoRatio.toFixed(2) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">最大连续盈利</div>
              <div class="metric-value">{{ maxConsecutiveWins }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">最大连续亏损</div>
              <div class="metric-value">{{ maxConsecutiveLosses }}</div>
            </div>
          </el-col>
        </el-row>
      </div>
    </el-card>

    <!-- Symbol-wise Analysis -->
    <el-card shadow="never" class="symbol-analysis-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>交易对分析</span>
          </div>
        </div>
      </template>
      
      <div class="symbol-analysis-container">
        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>交易对盈亏分布</h3>
              <div ref="symbolPnlChartRef" class="symbol-chart"></div>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>交易对交易次数</h3>
              <div ref="symbolTradesChartRef" class="symbol-chart"></div>
            </div>
          </el-col>
        </el-row>
        
        <div class="symbol-table-container">
          <h3>交易对详细数据</h3>
          <el-table
            :data="symbolPerformance"
            style="width: 100%"
            border
            stripe
            size="small"
          >
            <el-table-column prop="symbol" label="交易对" width="120">
              <template #default="scope">
                <div class="symbol-cell">
                  <crypto-icon :symbol="getCryptoSymbol(scope.row.symbol)" class="crypto-icon" />
                  <span>{{ scope.row.symbol }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="trades" label="交易次数" width="100" sortable />
            <el-table-column prop="winRate" label="胜率" width="100" sortable>
              <template #default="scope">
                {{ formatPercentage(scope.row.winRate) }}
              </template>
            </el-table-column>
            <el-table-column prop="totalPnl" label="总盈亏" width="150" sortable>
              <template #default="scope">
                <span :class="{ 'profit': scope.row.totalPnl > 0, 'loss': scope.row.totalPnl < 0 }">
                  {{ formatCurrency(scope.row.totalPnl) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="avgPnl" label="平均盈亏" width="150" sortable>
              <template #default="scope">
                <span :class="{ 'profit': scope.row.avgPnl > 0, 'loss': scope.row.avgPnl < 0 }">
                  {{ formatCurrency(scope.row.avgPnl) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="avgHoldingTime" label="平均持仓时间" width="150" />
            <el-table-column prop="profitFactor" label="盈亏因子" width="120" sortable>
              <template #default="scope">
                {{ scope.row.profitFactor.toFixed(2) }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </el-card>

    <!-- Strategy Performance -->
    <el-card shadow="never" class="strategy-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>策略绩效</span>
          </div>
        </div>
      </template>
      
      <div class="strategy-analysis-container">
        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>策略盈亏对比</h3>
              <div ref="strategyPnlChartRef" class="strategy-chart"></div>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>策略胜率对比</h3>
              <div ref="strategyWinRateChartRef" class="strategy-chart"></div>
            </div>
          </el-col>
        </el-row>
        
        <div class="strategy-table-container">
          <h3>策略详细数据</h3>
          <el-table
            :data="strategyPerformance"
            style="width: 100%"
            border
            stripe
            size="small"
          >
            <el-table-column prop="name" label="策略名称" width="150" />
            <el-table-column prop="trades" label="交易次数" width="100" sortable />
            <el-table-column prop="winRate" label="胜率" width="100" sortable>
              <template #default="scope">
                {{ formatPercentage(scope.row.winRate) }}
              </template>
            </el-table-column>
            <el-table-column prop="totalPnl" label="总盈亏" width="150" sortable>
              <template #default="scope">
                <span :class="{ 'profit': scope.row.totalPnl > 0, 'loss': scope.row.totalPnl < 0 }">
                  {{ formatCurrency(scope.row.totalPnl) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="avgPnl" label="平均盈亏" width="150" sortable>
              <template #default="scope">
                <span :class="{ 'profit': scope.row.avgPnl > 0, 'loss': scope.row.avgPnl < 0 }">
                  {{ formatCurrency(scope.row.avgPnl) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="avgHoldingTime" label="平均持仓时间" width="150" />
            <el-table-column prop="sharpeRatio" label="夏普比率" width="120" sortable>
              <template #default="scope">
                {{ scope.row.sharpeRatio.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column prop="maxDrawdown" label="最大回撤" width="120" sortable>
              <template #default="scope">
                {{ formatPercentage(scope.row.maxDrawdown) }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </el-card>

    <!-- Risk Analysis -->
    <el-card shadow="never" class="risk-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>风险分析</span>
          </div>
        </div>
      </template>
      
      <div class="risk-analysis-container">
        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>每月回撤分析</h3>
              <div ref="monthlyDrawdownChartRef" class="risk-chart"></div>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>风险收益比</h3>
              <div ref="riskRewardChartRef" class="risk-chart"></div>
            </div>
          </el-col>
        </el-row>
        
        <el-row :gutter="20" class="risk-metrics">
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">平均风险收益比</div>
              <div class="metric-value">{{ avgRiskRewardRatio.toFixed(2) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">风险调整后收益</div>
              <div class="metric-value" :class="{ 'profit': riskAdjustedReturn > 0, 'loss': riskAdjustedReturn < 0 }">
                {{ formatPercentage(riskAdjustedReturn) }}
              </div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">波动率</div>
              <div class="metric-value">{{ formatPercentage(volatility) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">贝塔系数</div>
              <div class="metric-value">{{ beta.toFixed(2) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">最大回撤持续时间</div>
              <div class="metric-value">{{ maxDrawdownDuration }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">回撤恢复时间</div>
              <div class="metric-value">{{ recoveryTime }}</div>
            </div>
          </el-col>
        </el-row>
      </div>
    </el-card>

    <!-- Time-based Analysis -->
    <el-card shadow="never" class="time-analysis-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>时间分析</span>
          </div>
        </div>
      </template>
      
      <div class="time-analysis-container">
        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>每日交易分布</h3>
              <div ref="dailyTradesChartRef" class="time-chart"></div>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>每小时交易分布</h3>
              <div ref="hourlyTradesChartRef" class="time-chart"></div>
            </div>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>每月盈亏</h3>
              <div ref="monthlyPnlChartRef" class="time-chart"></div>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>每周盈亏</h3>
              <div ref="weeklyPnlChartRef" class="time-chart"></div>
            </div>
          </el-col>
        </el-row>
      </div>
    </el-card>

    <!-- Trade Detail Dialog -->
    <el-dialog
      v-model="detailDialogVisible"
      title="交易详情"
      width="800px"
      destroy-on-close
    >
      <div v-if="currentTrade" class="trade-detail-dialog">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="交易ID">{{ currentTrade.id }}</el-descriptions-item>
          <el-descriptions-item label="交易对">{{ currentTrade.symbol }}</el-descriptions-item>
          <el-descriptions-item label="方向">
            <el-tag :type="currentTrade.direction === 'long' ? 'success' : 'danger'">
              {{ currentTrade.direction === 'long' ? '多' : '空' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="开仓价格">{{ formatCurrency(currentTrade.entryPrice) }}</el-descriptions-item>
          <el-descriptions-item label="平仓价格">{{ formatCurrency(currentTrade.exitPrice) }}</el-descriptions-item>
          <el-descriptions-item label="数量">{{ formatNumber(currentTrade.amount) }}</el-descriptions-item>
          <el-descriptions-item label="杠杆">{{ currentTrade.leverage }}x</el-descriptions-item>
          <el-descriptions-item label="已实现盈亏">
            <span :class="{ 'profit': currentTrade.realizedPnl > 0, 'loss': currentTrade.realizedPnl < 0 }">
              {{ formatCurrency(currentTrade.realizedPnl) }}
              ({{ formatPercentage(currentTrade.realizedPnlPercentage) }})
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="保证金">{{ formatCurrency(currentTrade.margin) }}</el-descriptions-item>
          <el-descriptions-item label="开仓时间">{{ formatDateTime(currentTrade.openTime) }}</el-descriptions-item>
          <el-descriptions-item label="平仓时间">{{ formatDateTime(currentTrade.closeTime) }}</el-descriptions-item>
          <el-descriptions-item label="持仓时间">{{ currentTrade.holdingTime }}</el-descriptions-item>
          <el-descriptions-item label="账户">{{ currentTrade.accountName }}</el-descriptions-item>
          <el-descriptions-item label="策略">{{ currentTrade.strategyName || '手动' }}</el-descriptions-item>
          <el-descriptions-item label="平仓原因">{{ getCloseReasonText(currentTrade.closeReason) }}</el-descriptions-item>
          <el-descriptions-item label="资金费率">{{ formatPercentage(currentTrade.fundingRate || 0) }}</el-descriptions-item>
          <el-descriptions-item label="资金费用">{{ formatCurrency(currentTrade.fundingFee || 0) }}</el-descriptions-item>
          <el-descriptions-item label="交易手续费">{{ formatCurrency(currentTrade.fee || 0) }}</el-descriptions-item>
        </el-descriptions>
        
        <div class="trade-detail-charts">
          <h3>价格走势</h3>
          <div ref="detailPriceChartRef" class="detail-chart"></div>
        </div>
        
        <div class="trade-detail-actions">
          <el-button type="primary" @click="repeatTrade(currentTrade)">再次交易</el-button>
          <el-button type="success" @click="exportTradeDetail(currentTrade)">导出详情</el-button>
        </div>
      </div>
    </el-dialog>

    <!-- Table Settings Dialog -->
    <el-dialog
      v-model="showTableSettings"
      title="表格设置"
      width="500px"
    >
      <div class="table-settings">
        <h3>显示列</h3>
        <el-checkbox-group v-model="visibleColumns">
          <el-checkbox v-for="column in allColumns" :key="column.prop" :label="column.prop">
            {{ column.label }}
          </el-checkbox>
        </el-checkbox-group>
        
        <h3>每页显示行数</h3>
        <el-radio-group v-model="pageSize">
          <el-radio :label="10">10</el-radio>
          <el-radio :label="20">20</el-radio>
          <el-radio :label="50">50</el-radio>
          <el-radio :label="100">100</el-radio>
        </el-radio-group>
      </div>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showTableSettings = false">取消</el-button>
          <el-button type="primary" @click="saveTableSettings">保存</el-button>
          <el-button type="info" @click="resetTableSettings">重置默认</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import { format, parseISO, formatDistance, subDays } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import { 
  Histogram, 
  ArrowDown, 
  ArrowUp, 
  Refresh, 
  Download, 
  Search,
  Setting, 
  View, 
  RefreshRight, 
  Document 
} from '@element-plus/icons-vue'
import { 
  getTradingHistory, 
  getTradingAnalytics,
  getTradeDetail,
  getSymbolPerformance,
  getStrategyPerformance,
  getRiskAnalytics,
  getTimeAnalytics
} from '@/api/trading'
import CryptoIcon from '@/components/CryptoIcon/index.vue'
import { exportToExcel, exportToCsv, exportToJson, exportToPdf } from '@/utils/export'

const router = useRouter()

// State variables
const loading = ref(false)
const pnlLoading = ref(false)
const advancedSearchVisible = ref(false)
const detailDialogVisible = ref(false)
const showTableSettings = ref(false)
const currentTrade = ref<any>(null)
const selectedTrades = ref<any[]>([])
const historyTableRef = ref<any>(null)
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const timeRange = ref('30d')
const pnlTimeRange = ref('30d')

// Chart references
let cumulativePnlChart: echarts.ECharts | null = null
let dailyPnlChart: echarts.ECharts | null = null
let pnlDistributionChart: echarts.ECharts | null = null
let drawdownChart: echarts.ECharts | null = null
let symbolPnlChart: echarts.ECharts | null = null
let symbolTradesChart: echarts.ECharts | null = null
let strategyPnlChart: echarts.ECharts | null = null
let strategyWinRateChart: echarts.ECharts | null = null
let monthlyDrawdownChart: echarts.ECharts | null = null
let riskRewardChart: echarts.ECharts | null = null
let dailyTradesChart: echarts.ECharts | null = null
let hourlyTradesChart: echarts.ECharts | null = null
let monthlyPnlChart: echarts.ECharts | null = null
let weeklyPnlChart: echarts.ECharts | null = null
let detailPriceChart: echarts.ECharts | null = null

const cumulativePnlChartRef = ref<HTMLElement | null>(null)
const dailyPnlChartRef = ref<HTMLElement | null>(null)
const pnlDistributionChartRef = ref<HTMLElement | null>(null)
const drawdownChartRef = ref<HTMLElement | null>(null)
const symbolPnlChartRef = ref<HTMLElement | null>(null)
const symbolTradesChartRef = ref<HTMLElement | null>(null)
const strategyPnlChartRef = ref<HTMLElement | null>(null)
const strategyWinRateChartRef = ref<HTMLElement | null>(null)
const monthlyDrawdownChartRef = ref<HTMLElement | null>(null)
const riskRewardChartRef = ref<HTMLElement | null>(null)
const dailyTradesChartRef = ref<HTMLElement | null>(null)
const hourlyTradesChartRef = ref<HTMLElement | null>(null)
const monthlyPnlChartRef = ref<HTMLElement | null>(null)
const weeklyPnlChartRef = ref<HTMLElement | null>(null)
const detailPriceChartRef = ref<HTMLElement | null>(null)

// Data
const tradingHistory = ref<any[]>([])
const symbolPerformance = ref<any[]>([])
const strategyPerformance = ref<any[]>([])

// Filter form
const filterForm = reactive({
  dateRange: [
    format(subDays(new Date(), 30), 'yyyy-MM-dd'),
    format(new Date(), 'yyyy-MM-dd')
  ] as [string, string],
  symbol: '',
  direction: '',
  strategy: '',
  pnlStatus: ''
})

// Advanced filter form
const advancedFilterForm = reactive({
  holdingTime: '',
  leverageRange: [1, 125],
  pnlRange: [-100, 100],
  account: '',
  closeReason: ''
})

// Options
const symbolOptions = [
  { label: 'ETH/USDT', value: 'ETH-USDT' },
  { label: 'BTC/USDT', value: 'BTC-USDT' },
  { label: 'SOL/USDT', value: 'SOL-USDT' },
  { label: 'BNB/USDT', value: 'BNB-USDT' },
  { label: 'XRP/USDT', value: 'XRP-USDT' },
  { label: 'ADA/USDT', value: 'ADA-USDT' },
  { label: 'DOGE/USDT', value: 'DOGE-USDT' },
  { label: 'AVAX/USDT', value: 'AVAX-USDT' },
  { label: 'DOT/USDT', value: 'DOT-USDT' },
  { label: 'MATIC/USDT', value: 'MATIC-USDT' }
]

const strategyOptions = [
  { label: 'RSI分层策略', value: 'rsi_layered' },
  { label: 'MACD策略', value: 'macd' },
  { label: '布林带策略', value: 'bollinger' },
  { label: '双均线策略', value: 'dual_ma' },
  { label: '网格交易', value: 'grid' }
]

const accountOptions = [
  { label: 'OKX主账户', value: '1' },
  { label: 'OKX子账户1', value: '2' },
  { label: 'OKX子账户2', value: '3' },
  { label: 'Binance账户', value: '4' }
]

// Table columns
const allColumns = [
  { prop: 'symbol', label: '交易对', width: 120 },
  { prop: 'direction', label: '方向', width: 80 },
  { prop: 'entryPrice', label: '开仓价', width: 120 },
  { prop: 'exitPrice', label: '平仓价', width: 120 },
  { prop: 'amount', label: '数量', width: 120 },
  { prop: 'leverage', label: '杠杆', width: 80 },
  { prop: 'realizedPnl', label: '已实现盈亏', width: 150 },
  { prop: 'holdingTime', label: '持仓时间', width: 120 },
  { prop: 'closeReason', label: '平仓原因', width: 120 },
  { prop: 'closeTime', label: '平仓时间', width: 160 }
]

const visibleColumns = ref(allColumns.map(col => col.prop))

// Performance metrics
const totalReturn = ref(0)
const annualizedReturn = ref(0)
const sharpeRatio = ref(0)
const maxDrawdown = ref(0)
const calmarRatio = ref(0)
const sortinoRatio = ref(0)
const maxConsecutiveWins = ref(0)
const maxConsecutiveLosses = ref(0)
const avgRiskRewardRatio = ref(0)
const riskAdjustedReturn = ref(0)
const volatility = ref(0)
const beta = ref(0)
const maxDrawdownDuration = ref('')
const recoveryTime = ref('')

// Computed properties
const filteredHistory = computed(() => {
  let result = [...tradingHistory.value]
  
  // Apply filters
  if (filterForm.symbol) {
    result = result.filter(t => t.symbol === filterForm.symbol)
  }
  
  if (filterForm.direction) {
    result = result.filter(t => t.direction === filterForm.direction)
  }
  
  if (filterForm.strategy) {
    result = result.filter(t => t.strategyId === filterForm.strategy)
  }
  
  if (filterForm.pnlStatus) {
    if (filterForm.pnlStatus === 'profit') {
      result = result.filter(t => t.realizedPnl > 0)
    } else if (filterForm.pnlStatus === 'loss') {
      result = result.filter(t => t.realizedPnl < 0)
    }
  }
  
  // Apply advanced filters
  if (advancedFilterForm.holdingTime) {
    switch (advancedFilterForm.holdingTime) {
      case 'lt_1h':
        result = result.filter(t => {
          const openTime = new Date(t.openTime).getTime()
          const closeTime = new Date(t.closeTime).getTime()
          return (closeTime - openTime) < 60 * 60 * 1000
        })
        break
      case '1h_24h':
        result = result.filter(t => {
          const openTime = new Date(t.openTime).getTime()
          const closeTime = new Date(t.closeTime).getTime()
          const diff = closeTime - openTime
          return diff >= 60 * 60 * 1000 && diff < 24 * 60 * 60 * 1000
        })
        break
      case '1d_7d':
        result = result.filter(t => {
          const openTime = new Date(t.openTime).getTime()
          const closeTime = new Date(t.closeTime).getTime()
          const diff = closeTime - openTime
          return diff >= 24 * 60 * 60 * 1000 && diff < 7 * 24 * 60 * 60 * 1000
        })
        break
      case 'gt_7d':
        result = result.filter(t => {
          const openTime = new Date(t.openTime).getTime()
          const closeTime = new Date(t.closeTime).getTime()
          return (closeTime - openTime) >= 7 * 24 * 60 * 60 * 1000
        })
        break
    }
  }
  
  if (advancedFilterForm.leverageRange && advancedFilterForm.leverageRange.length === 2) {
    const [min, max] = advancedFilterForm.leverageRange
    result = result.filter(t => t.leverage >= min && t.leverage <= max)
  }
  
  if (advancedFilterForm.pnlRange && advancedFilterForm.pnlRange.length === 2) {
    const [min, max] = advancedFilterForm.pnlRange
    result = result.filter(t => {
      const pnlPercentage = t.realizedPnlPercentage
      return pnlPercentage >= min && pnlPercentage <= max
    })
  }
  
  if (advancedFilterForm.account) {
    result = result.filter(t => t.accountId === advancedFilterForm.account)
  }
  
  if (advancedFilterForm.closeReason) {
    result = result.filter(t => t.closeReason === advancedFilterForm.closeReason)
  }
  
  // Apply search keyword
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(t => 
      t.symbol.toLowerCase().includes(keyword) ||
      t.id?.toString().includes(keyword) ||
      t.accountName?.toLowerCase().includes(keyword) ||
      t.strategyName?.toLowerCase().includes(keyword)
    )
  }
  
  return result
})

const paginatedHistory = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredHistory.value.slice(start, end)
})

const totalTrades = computed(() => tradingHistory.value.length)
const longTrades = computed(() => tradingHistory.value.filter(t => t.direction === 'long').length)
const shortTrades = computed(() => tradingHistory.value.filter(t => t.direction === 'short').length)
const totalPnl = computed(() => {
  return tradingHistory.value.reduce((sum, t) => sum + t.realizedPnl, 0)
})
const totalPnlPercentage = computed(() => {
  const totalMargin = tradingHistory.value.reduce((sum, t) => sum + t.margin, 0)
  if (totalMargin === 0) return 0
  return (totalPnl.value / totalMargin) * 100
})
const winRate = computed(() => {
  const totalTrades = tradingHistory.value.length
  if (totalTrades === 0) return 0
  
  const winningTrades = tradingHistory.value.filter(t => t.realizedPnl > 0).length
  return (winningTrades / totalTrades) * 100
})
const winRateColor = computed(() => {
  if (winRate.value < 40) return '#f56c6c'
  if (winRate.value < 50) return '#e6a23c'
  return '#67c23a'
})
const profitLossRatio = computed(() => {
  const winningTrades = tradingHistory.value.filter(t => t.realizedPnl > 0)
  const losingTrades = tradingHistory.value.filter(t => t.realizedPnl < 0)
  
  if (losingTrades.length === 0) return winningTrades.length > 0 ? 999 : 0
  
  const avgProfit = winningTrades.length > 0 
    ? winningTrades.reduce((sum, t) => sum + t.realizedPnl, 0) / winningTrades.length 
    : 0
    
  const avgLoss = losingTrades.length > 0 
    ? Math.abs(losingTrades.reduce((sum, t) => sum + t.realizedPnl, 0) / losingTrades.length)
    : 1
    
  return avgProfit / avgLoss
})
const avgProfit = computed(() => {
  const winningTrades = tradingHistory.value.filter(t => t.realizedPnl > 0)
  if (winningTrades.length === 0) return 0
  return winningTrades.reduce((sum, t) => sum + t.realizedPnl, 0) / winningTrades.length
})

// Methods
// Format utilities
const formatCurrency = (value: number) => {
  if (value === undefined || value === null || isNaN(value)) return '0.00'
  
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    })
  } else {
    return value.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 6
    })
  }
}

const formatNumber = (value: number) => {
  if (value === undefined || value === null || isNaN(value)) return '0'
  
  if (value >= 1000) {
    return value.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    })
  } else {
    return value.toLocaleString('en-US', {
      minimumFractionDigits: 4,
      maximumFractionDigits: 8
    })
  }
}

const formatPercentage = (value: number) => {
  if (value === undefined || value === null || isNaN(value)) return '0.00%'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

const formatDateTime = (dateStr: string) => {
  if (!dateStr) return ''
  try {
    const date = typeof dateStr === 'string' ? parseISO(dateStr) : new Date(dateStr)
    return format(date, 'yyyy-MM-dd HH:mm:ss', { locale: zhCN })
  } catch (e) {
    return dateStr
  }
}

const getCryptoSymbol = (symbol: string) => {
  return symbol.split('-')[0].toLowerCase()
}

const getCloseReasonText = (reason: string) => {
  switch (reason) {
    case 'manual': return '手动平仓'
    case 'take_profit': return '止盈触发'
    case 'stop_loss': return '止损触发'
    case 'liquidation': return '强制平仓'
    case 'strategy': return '策略信号'
    case 'system': return '系统平仓'
    default: return reason
  }
}

// Data loading functions
const refreshHistory = async () => {
  try {
    loading.value = true
    
    const { data } = await getTradingHistory({
      timeRange: timeRange.value
    })
    
    tradingHistory.value = data.trades || []
    
    // Initialize trade charts after data is loaded
    nextTick(() => {
      tradingHistory.value.forEach(trade => {
        if (trade.priceHistory) {
          initTradePriceChart(trade)
        }
      })
    })
    
    ElMessage.success('交易历史数据已刷新')
    
    // Load analytics data
    loadAnalyticsData()
  } catch (err) {
    console.error('加载交易历史失败:', err)
    ElMessage.error('加载交易历史失败')
  } finally {
    loading.value = false
  }
}

const loadAnalyticsData = async () => {
  try {
    pnlLoading.value = true
    
    // Load P&L analytics
    const pnlAnalytics = await getTradingAnalytics({
      timeRange: pnlTimeRange.value
    })
    
    // Update performance metrics
    totalReturn.value = pnlAnalytics.data.totalReturn
    annualizedReturn.value = pnlAnalytics.data.annualizedReturn
    sharpeRatio.value = pnlAnalytics.data.sharpeRatio
    maxDrawdown.value = pnlAnalytics.data.maxDrawdown
    calmarRatio.value = pnlAnalytics.data.calmarRatio
    sortinoRatio.value = pnlAnalytics.data.sortinoRatio
    maxConsecutiveWins.value = pnlAnalytics.data.maxConsecutiveWins
    maxConsecutiveLosses.value = pnlAnalytics.data.maxConsecutiveLosses
    
    // Load symbol performance
    const symbolAnalytics = await getSymbolPerformance({
      timeRange: pnlTimeRange.value
    })
    symbolPerformance.value = symbolAnalytics.data.symbols || []
    
    // Load strategy performance
    const strategyAnalytics = await getStrategyPerformance({
      timeRange: pnlTimeRange.value
    })
    strategyPerformance.value = strategyAnalytics.data.strategies || []
    
    // Load risk analytics
    const riskAnalytics = await getRiskAnalytics({
      timeRange: pnlTimeRange.value
    })
    avgRiskRewardRatio.value = riskAnalytics.data.avgRiskRewardRatio
    riskAdjustedReturn.value = riskAnalytics.data.riskAdjustedReturn
    volatility.value = riskAnalytics.data.volatility
    beta.value = riskAnalytics.data.beta
    maxDrawdownDuration.value = riskAnalytics.data.maxDrawdownDuration
    recoveryTime.value = riskAnalytics.data.recoveryTime
    
    // Load time analytics
    const timeAnalytics = await getTimeAnalytics({
      timeRange: pnlTimeRange.value
    })
    
    // Initialize charts
    nextTick(() => {
      initPnlCharts(pnlAnalytics.data)
      initSymbolCharts(symbolAnalytics.data)
      initStrategyCharts(strategyAnalytics.data)
      initRiskCharts(riskAnalytics.data)
      initTimeCharts(timeAnalytics.data)
    })
  } catch (err) {
    console.error('加载分析数据失败:', err)
    ElMessage.error('加载分析数据失败')
  } finally {
    pnlLoading.value = false
  }
}

const loadTradeDetail = async (tradeId: string) => {
  try {
    const { data } = await getTradeDetail(tradeId)
    currentTrade.value = data
    
    // Initialize detail chart
    nextTick(() => {
      initDetailPriceChart(data)
    })
  } catch (err) {
    console.error('加载交易详情失败:', err)
    ElMessage.error('加载交易详情失败')
  }
}

// Chart initialization functions
const initTradePriceChart = (trade: any) => {
  const chartId = `price-chart-${trade.id}`
  const chartElement = document.getElementById(chartId)
  
  if (!chartElement) return
  
  const chart = echarts.init(chartElement)
  
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross'
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: trade.priceHistory.map((item: any) => item.time)
    },
    yAxis: {
      type: 'value',
      scale: true
    },
    series: [
      {
        name: '价格',
        type: 'line',
        data: trade.priceHistory.map((item: any) => item.price),
        markPoint: {
          data: [
            { name: '开仓', coord: [trade.priceHistory[0].time, trade.entryPrice], value: trade.entryPrice, itemStyle: { color: '#409EFF' } },
            { name: '平仓', coord: [trade.priceHistory[trade.priceHistory.length - 1].time, trade.exitPrice], value: trade.exitPrice, itemStyle: { color: trade.realizedPnl > 0 ? '#67C23A' : '#F56C6C' } }
          ]
        }
      }
    ]
  }
  
  chart.setOption(option)
}

const initPnlCharts = (data: any) => {
  // Cumulative PnL Chart
  if (cumulativePnlChartRef.value) {
    if (!cumulativePnlChart) {
      cumulativePnlChart = echarts.init(cumulativePnlChartRef.value)
    }
    
    const cumulativeOption = {
      tooltip: {
        trigger: 'axis',
        formatter: function(params: any) {
          const date = params[0].axisValue
          const value = params[0].data
          return `${date}<br/>累计盈亏: ${formatCurrency(value)}`
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: data.cumulativePnl.map((item: any) => item.date)
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: {
          formatter: (value: number) => formatCurrency(value)
        }
      },
      series: [
        {
          name: '累计盈亏',
          type: 'line',
          data: data.cumulativePnl.map((item: any) => item.value),
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(103, 194, 58, 0.5)' },
              { offset: 1, color: 'rgba(103, 194, 58, 0.1)' }
            ])
          },
          lineStyle: {
            width: 2,
            color: '#67C23A'
          },
          markLine: {
            data: [
              { type: 'max', name: '最高点' },
              { type: 'min', name: '最低点' }
            ]
          }
        }
      ]
    }
    
    cumulativePnlChart.setOption(cumulativeOption)
  }
  
  // Daily PnL Chart
  if (dailyPnlChartRef.value) {
    if (!dailyPnlChart) {
      dailyPnlChart = echarts.init(dailyPnlChartRef.value)
    }
    
    const dailyOption = {
      tooltip: {
        trigger: 'axis',
        formatter: function(params: any) {
          const date = params[0].axisValue
          const value = params[0].data
          return `${date}<br/>日盈亏: ${formatCurrency(value)}`
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: data.dailyPnl.map((item: any) => item.date)
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: {
          formatter: (value: number) => formatCurrency(value)
        }
      },
      series: [
        {
          name: '日盈亏',
          type: 'bar',
          data: data.dailyPnl.map((item: any) => item.value),
          itemStyle: {
            color: function(params: any) {
              return params.value >= 0 ? '#67C23A' : '#F56C6C'
            }
          }
        }
      ]
    }
    
    dailyPnlChart.setOption(dailyOption)
  }
  
  // PnL Distribution Chart
  if (pnlDistributionChartRef.value) {
    if (!pnlDistributionChart) {
      pnlDistributionChart = echarts.init(pnlDistributionChartRef.value)
    }
    
    const distributionOption = {
      tooltip: {
        trigger: 'item',
        formatter: function(params: any) {
          return `${params.name}: ${params.value} 次 (${params.percent}%)`
        }
      },
      legend: {
        orient: 'vertical',
        right: 10,
        top: 'center'
      },
      series: [
        {
          name: '盈亏分布',
          type: 'pie',
          radius: ['40%', '70%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 10,
            borderColor: '#fff',
            borderWidth: 2
          },
          label: {
            show: false,
            position: 'center'
          },
          emphasis: {
            label: {
              show: true,
              fontSize: '16',
              fontWeight: 'bold'
            }
          },
          labelLine: {
            show: false
          },
          data: [
            { value: data.pnlDistribution.profit, name: '盈利', itemStyle: { color: '#67C23A' } },
            { value: data.pnlDistribution.loss, name: '亏损', itemStyle: { color: '#F56C6C' } }
          ]
        }
      ]
    }
    
    pnlDistributionChart.setOption(distributionOption)
  }
  
  // Drawdown Chart
  if (drawdownChartRef.value) {
    if (!drawdownChart) {
      drawdownChart = echarts.init(drawdownChartRef.value)
    }
    
    const drawdownOption = {
      tooltip: {
        trigger: 'axis',
        formatter: function(params: any) {
          const date = params[0].axisValue
          const value = params[0].data
          return `${date}<br/>回撤: ${formatPercentage(value)}`
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: data.drawdown.map((item: any) => item.date)
      },
      yAxis: {
        type: 'value',
        scale: true,
        inverse: true,
        axisLabel: {
          formatter: (value: number) => formatPercentage(value)
        }
      },
      series: [
        {
          name: '回撤',
          type: 'line',
          data: data.drawdown.map((item: any) => item.value),
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(245, 108, 108, 0.1)' },
              { offset: 1, color: 'rgba(245, 108, 108, 0.5)' }
            ])
          },
          lineStyle: {
            width: 2,
            color: '#F56C6C'
          },
          markLine: {
            data: [
              { type: 'min', name: '最大回撤' }
            ]
          }
        }
      ]
    }
    
    drawdownChart.setOption(drawdownOption)
  }
}

const initSymbolCharts = (data: any) => {
  // Symbol PnL Chart
  if (symbolPnlChartRef.value) {
    if (!symbolPnlChart) {
      symbolPnlChart = echarts.init(symbolPnlChartRef.value)
    }
    
    const symbolPnlOption = {
      tooltip: {
        trigger: 'item',
        formatter: function(params: any) {
          return `${params.name}: ${formatCurrency(params.value)}`
        }
      },
      legend: {
        orient: 'vertical',
        right: 10,
        top: 'center',
        type: 'scroll'
      },
      series: [
        {
          name: '交易对盈亏',
          type: 'pie',
          radius: '70%',
          data: data.symbolPnl.map((item: any) => ({
            name: item.symbol,
            value: item.pnl,
            itemStyle: {
              color: item.pnl >= 0 ? '#67C23A' : '#F56C6C'
            }
          })),
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)'
            }
          }
        }
      ]
    }
    
    symbolPnlChart.setOption(symbolPnlOption)
  }
  
  // Symbol Trades Chart
  if (symbolTradesChartRef.value) {
    if (!symbolTradesChart) {
      symbolTradesChart = echarts.init(symbolTradesChartRef.value)
    }
    
    const symbolTradesOption = {
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow'
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: data.symbolTrades.map((item: any) => item.symbol),
        axisLabel: {
          interval: 0,
          rotate: 30
        }
      },
      yAxis: {
        type: 'value'
      },
      series: [
        {
          name: '交易次数',
          type: