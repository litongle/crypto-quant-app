<template>
  <div class="positions-container">
    <!-- Page header with title and actions -->
    <div class="page-header">
      <div class="header-title">
        <el-icon><Position /></el-icon>
        <h2>持仓管理</h2>
      </div>
      <div class="header-actions">
        <el-button-group>
          <el-button
            type="primary"
            :icon="Refresh"
            :loading="loading"
            @click="refreshPositions"
          >
            刷新
          </el-button>
          <el-button
            type="success"
            :icon="Plus"
            @click="openCreatePositionDialog"
          >
            新建持仓
          </el-button>
          <el-button
            type="danger"
            :icon="Delete"
            :disabled="!hasSelectedPositions"
            @click="confirmBatchClose"
          >
            批量平仓
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
          
          <el-form-item label="风险等级">
            <el-select
              v-model="filterForm.riskLevel"
              placeholder="风险等级"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="低" value="low" />
              <el-option label="中" value="medium" />
              <el-option label="高" value="high" />
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
          
          <el-form-item label="创建时间">
            <el-date-picker
              v-model="advancedFilterForm.dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
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
        </el-form>
      </div>
    </el-card>

    <!-- Statistics cards -->
    <div class="statistics-cards">
      <el-row :gutter="16">
        <el-col :xs="24" :sm="12" :md="6">
          <el-card shadow="hover" class="statistic-card">
            <div class="statistic-title">总持仓数</div>
            <div class="statistic-value">{{ totalPositions }}</div>
            <div class="statistic-footer">
              <span>多: {{ longPositions }}</span>
              <span>空: {{ shortPositions }}</span>
            </div>
          </el-card>
        </el-col>
        
        <el-col :xs="24" :sm="12" :md="6">
          <el-card shadow="hover" class="statistic-card">
            <div class="statistic-title">总持仓价值</div>
            <div class="statistic-value">{{ formatCurrency(totalPositionValue) }}</div>
            <div class="statistic-footer">
              <span>占账户比例: {{ totalPositionRatio }}%</span>
            </div>
          </el-card>
        </el-col>
        
        <el-col :xs="24" :sm="12" :md="6">
          <el-card shadow="hover" class="statistic-card">
            <div class="statistic-title">未实现盈亏</div>
            <div 
              class="statistic-value" 
              :class="{ 'profit': totalUnrealizedPnl > 0, 'loss': totalUnrealizedPnl < 0 }"
            >
              {{ formatCurrency(totalUnrealizedPnl) }}
            </div>
            <div class="statistic-footer">
              <span>{{ formatPercentage(totalUnrealizedPnlPercentage) }}</span>
            </div>
          </el-card>
        </el-col>
        
        <el-col :xs="24" :sm="12" :md="6">
          <el-card shadow="hover" class="statistic-card">
            <div class="statistic-title">风险评估</div>
            <div class="statistic-value">
              <el-progress
                :percentage="riskPercentage"
                :color="riskColor"
                :stroke-width="10"
                :format="() => riskLevel"
              />
            </div>
            <div class="statistic-footer">
              <span>最大回撤: {{ formatPercentage(maxDrawdown) }}</span>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- Positions table -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>当前持仓</span>
            <el-tag type="info" size="small">{{ filteredPositions.length }}</el-tag>
          </div>
          <div class="header-right">
            <el-input
              v-model="searchKeyword"
              placeholder="搜索持仓..."
              prefix-icon="Search"
              clearable
              @input="handleSearch"
            />
            <el-tooltip content="表格设置" placement="top">
              <el-button :icon="Setting" circle @click="showTableSettings = true" />
            </el-tooltip>
            <el-switch
              v-model="autoRefresh"
              active-text="自动刷新"
              inactive-text="手动刷新"
              @change="toggleAutoRefresh"
            />
          </div>
        </div>
      </template>
      
      <!-- Table loading state -->
      <div v-if="loading" class="loading-container">
        <el-spin class="loading-spinner" />
        <span>加载持仓数据...</span>
      </div>
      
      <!-- Empty state -->
      <el-empty
        v-else-if="filteredPositions.length === 0"
        description="暂无持仓数据"
      >
        <template #image>
          <el-icon class="empty-icon"><Document /></el-icon>
        </template>
        <el-button type="primary" @click="refreshPositions">刷新数据</el-button>
      </el-empty>
      
      <!-- Positions table -->
      <el-table
        v-else
        ref="positionsTableRef"
        :data="filteredPositions"
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
            <div class="position-detail">
              <el-descriptions :column="3" border>
                <el-descriptions-item label="创建时间">
                  {{ formatDateTime(props.row.createdAt) }}
                </el-descriptions-item>
                <el-descriptions-item label="更新时间">
                  {{ formatDateTime(props.row.updatedAt) }}
                </el-descriptions-item>
                <el-descriptions-item label="持仓时间">
                  {{ calculateHoldingTime(props.row.createdAt) }}
                </el-descriptions-item>
                <el-descriptions-item label="账户">
                  {{ props.row.accountName }}
                </el-descriptions-item>
                <el-descriptions-item label="策略">
                  {{ props.row.strategyName || '手动' }}
                </el-descriptions-item>
                <el-descriptions-item label="资金费率">
                  {{ formatPercentage(props.row.fundingRate || 0) }}
                </el-descriptions-item>
                <el-descriptions-item label="强平价格">
                  {{ formatCurrency(props.row.liquidationPrice) }}
                </el-descriptions-item>
                <el-descriptions-item label="预计强平距离">
                  {{ formatPercentage(calculateLiquidationDistance(props.row)) }}
                </el-descriptions-item>
                <el-descriptions-item label="资金费用">
                  {{ formatCurrency(props.row.fundingFee || 0) }}
                </el-descriptions-item>
              </el-descriptions>
              
              <div class="position-charts">
                <div class="chart-container">
                  <div ref="pnlChartRef" :id="`pnl-chart-${props.row.id}`" class="pnl-chart"></div>
                </div>
                <div class="position-actions">
                  <el-button-group>
                    <el-button 
                      type="primary" 
                      :icon="Edit"
                      @click.stop="editPosition(props.row)"
                    >
                      编辑
                    </el-button>
                    <el-button 
                      type="success" 
                      :icon="Plus"
                      @click.stop="addToPosition(props.row)"
                    >
                      加仓
                    </el-button>
                    <el-button 
                      type="warning" 
                      :icon="Remove"
                      @click.stop="reducePosition(props.row)"
                    >
                      减仓
                    </el-button>
                    <el-button 
                      type="danger" 
                      :icon="Close"
                      @click.stop="confirmClosePosition(props.row)"
                    >
                      平仓
                    </el-button>
                  </el-button-group>
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
        
        <el-table-column prop="currentPrice" label="当前价" width="120" sortable>
          <template #default="scope">
            <div 
              class="price-cell" 
              :class="{
                'price-up': scope.row.priceChange > 0,
                'price-down': scope.row.priceChange < 0
              }"
            >
              {{ formatCurrency(scope.row.currentPrice) }}
              <el-icon v-if="scope.row.priceChange > 0"><CaretTop /></el-icon>
              <el-icon v-else-if="scope.row.priceChange < 0"><CaretBottom /></el-icon>
            </div>
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
        
        <el-table-column prop="margin" label="保证金" width="120" sortable>
          <template #default="scope">
            {{ formatCurrency(scope.row.margin) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="unrealizedPnl" label="未实现盈亏" width="150" sortable>
          <template #default="scope">
            <div 
              class="pnl-cell" 
              :class="{
                'profit': scope.row.unrealizedPnl > 0,
                'loss': scope.row.unrealizedPnl < 0
              }"
            >
              {{ formatCurrency(scope.row.unrealizedPnl) }}
              <span class="pnl-percentage">
                ({{ formatPercentage(scope.row.unrealizedPnlPercentage) }})
              </span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="stopLoss" label="止损" width="120">
          <template #default="scope">
            <div v-if="scope.row.stopLoss">
              {{ formatCurrency(scope.row.stopLoss) }}
            </div>
            <el-button 
              v-else 
              size="small" 
              type="danger" 
              plain
              @click.stop="setStopLoss(scope.row)"
            >
              设置止损
            </el-button>
          </template>
        </el-table-column>
        
        <el-table-column prop="takeProfit" label="止盈" width="120">
          <template #default="scope">
            <div v-if="scope.row.takeProfit">
              {{ formatCurrency(scope.row.takeProfit) }}
            </div>
            <el-button 
              v-else 
              size="small" 
              type="success" 
              plain
              @click.stop="setTakeProfit(scope.row)"
            >
              设置止盈
            </el-button>
          </template>
        </el-table-column>
        
        <el-table-column prop="riskLevel" label="风险" width="100">
          <template #default="scope">
            <el-tag
              :type="getRiskTagType(scope.row.riskLevel)"
              effect="plain"
            >
              {{ getRiskLevelText(scope.row.riskLevel) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="操作" fixed="right" width="200">
          <template #default="scope">
            <el-button-group>
              <el-tooltip content="编辑持仓" placement="top">
                <el-button 
                  type="primary" 
                  :icon="Edit" 
                  circle
                  @click.stop="editPosition(scope.row)"
                />
              </el-tooltip>
              <el-tooltip content="查看详情" placement="top">
                <el-button 
                  type="info" 
                  :icon="View" 
                  circle
                  @click.stop="viewPositionDetail(scope.row)"
                />
              </el-tooltip>
              <el-tooltip content="平仓" placement="top">
                <el-button 
                  type="danger" 
                  :icon="Close" 
                  circle
                  @click.stop="confirmClosePosition(scope.row)"
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
          :total="totalPositionsCount"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- Position History -->
    <el-card shadow="never" class="history-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>持仓历史</span>
            <el-tag type="info" size="small">{{ positionHistory.length }}</el-tag>
          </div>
          <div class="header-right">
            <el-date-picker
              v-model="historyDateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
              @change="loadPositionHistory"
            />
          </div>
        </div>
      </template>
      
      <div v-if="historyLoading" class="loading-container">
        <el-spin class="loading-spinner" />
        <span>加载历史数据...</span>
      </div>
      
      <el-empty
        v-else-if="positionHistory.length === 0"
        description="暂无历史数据"
      />
      
      <el-table
        v-else
        :data="positionHistory"
        style="width: 100%"
        border
        stripe
        size="small"
      >
        <el-table-column prop="symbol" label="交易对" width="120" />
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
        <el-table-column prop="entryPrice" label="开仓价" width="120">
          <template #default="scope">
            {{ formatCurrency(scope.row.entryPrice) }}
          </template>
        </el-table-column>
        <el-table-column prop="exitPrice" label="平仓价" width="120">
          <template #default="scope">
            {{ formatCurrency(scope.row.exitPrice) }}
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="数量" width="120">
          <template #default="scope">
            {{ formatNumber(scope.row.amount) }}
          </template>
        </el-table-column>
        <el-table-column prop="leverage" label="杠杆" width="80">
          <template #default="scope">
            {{ scope.row.leverage }}x
          </template>
        </el-table-column>
        <el-table-column prop="realizedPnl" label="已实现盈亏" width="150">
          <template #default="scope">
            <span 
              :class="{
                'profit': scope.row.realizedPnl > 0,
                'loss': scope.row.realizedPnl < 0
              }"
            >
              {{ formatCurrency(scope.row.realizedPnl) }}
              ({{ formatPercentage(scope.row.realizedPnlPercentage) }})
            </span>
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
        <el-table-column prop="closedAt" label="平仓时间" width="160">
          <template #default="scope">
            {{ formatDateTime(scope.row.closedAt) }}
          </template>
        </el-table-column>
      </el-table>
      
      <!-- History pagination -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="historyCurrentPage"
          v-model:page-size="historyPageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="totalHistoryCount"
          @size-change="handleHistorySizeChange"
          @current-change="handleHistoryCurrentChange"
        />
      </div>
    </el-card>

    <!-- Position Analytics -->
    <el-card shadow="never" class="analytics-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>持仓分析</span>
          </div>
          <div class="header-right">
            <el-radio-group v-model="analyticsTimeRange" size="small" @change="updateAnalytics">
              <el-radio-button label="7d">7天</el-radio-button>
              <el-radio-button label="30d">30天</el-radio-button>
              <el-radio-button label="90d">90天</el-radio-button>
              <el-radio-button label="all">全部</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </template>
      
      <div v-if="analyticsLoading" class="loading-container">
        <el-spin class="loading-spinner" />
        <span>加载分析数据...</span>
      </div>
      
      <div v-else class="analytics-container">
        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <div ref="pnlChartContainer" class="chart-container">
              <h3>盈亏走势</h3>
              <div ref="pnlTrendChartRef" class="analytics-chart"></div>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div ref="positionDistributionContainer" class="chart-container">
              <h3>持仓分布</h3>
              <div ref="positionDistributionChartRef" class="analytics-chart"></div>
            </div>
          </el-col>
        </el-row>
        <el-row :gutter="20" class="analytics-metrics">
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">胜率</div>
              <div class="metric-value">{{ formatPercentage(analytics.winRate) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">平均持仓时间</div>
              <div class="metric-value">{{ analytics.avgHoldingTime }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">平均盈亏比</div>
              <div class="metric-value">{{ analytics.profitLossRatio.toFixed(2) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">最大单笔盈利</div>
              <div class="metric-value profit">{{ formatCurrency(analytics.maxProfit) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">最大单笔亏损</div>
              <div class="metric-value loss">{{ formatCurrency(analytics.maxLoss) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">平均杠杆</div>
              <div class="metric-value">{{ analytics.avgLeverage.toFixed(1) }}x</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">交易频率</div>
              <div class="metric-value">{{ analytics.tradeFrequency }}/天</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">最大回撤</div>
              <div class="metric-value loss">{{ formatPercentage(analytics.maxDrawdown) }}</div>
            </div>
          </el-col>
        </el-row>
      </div>
    </el-card>

    <!-- Position Edit Dialog -->
    <el-dialog
      v-model="positionDialogVisible"
      :title="dialogType === 'create' ? '新建持仓' : '编辑持仓'"
      width="500px"
      destroy-on-close
    >
      <el-form
        ref="positionFormRef"
        :model="positionForm"
        :rules="positionRules"
        label-width="100px"
      >
        <el-form-item label="交易对" prop="symbol">
          <el-select
            v-model="positionForm.symbol"
            placeholder="选择交易对"
            filterable
            :disabled="dialogType === 'edit'"
          >
            <el-option
              v-for="item in symbolOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        
        <el-form-item label="方向" prop="direction">
          <el-radio-group v-model="positionForm.direction" :disabled="dialogType === 'edit'">
            <el-radio label="long">多</el-radio>
            <el-radio label="short">空</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item v-if="dialogType === 'create'" label="价格类型" prop="priceType">
          <el-radio-group v-model="positionForm.priceType">
            <el-radio label="market">市价</el-radio>
            <el-radio label="limit">限价</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item v-if="positionForm.priceType === 'limit'" label="限价" prop="price">
          <el-input-number
            v-model="positionForm.price"
            :precision="2"
            :step="0.01"
            :min="0"
            style="width: 100%"
          />
        </el-form-item>
        
        <el-form-item label="数量" prop="amount">
          <el-input-number
            v-model="positionForm.amount"
            :precision="4"
            :step="0.01"
            :min="0.0001"
            style="width: 100%"
          />
        </el-form-item>
        
        <el-form-item label="杠杆" prop="leverage">
          <el-slider
            v-model="positionForm.leverage"
            :min="1"
            :max="125"
            :step="1"
            :marks="{1: '1x', 25: '25x', 50: '50x', 75: '75x', 100: '100x', 125: '125x'}"
            :disabled="dialogType === 'edit'"
          />
        </el-form-item>
        
        <el-form-item label="止损价格" prop="stopLoss">
          <el-input-number
            v-model="positionForm.stopLoss"
            :precision="2"
            :step="0.01"
            :min="0"
            style="width: 100%"
          />
        </el-form-item>
        
        <el-form-item label="止盈价格" prop="takeProfit">
          <el-input-number
            v-model="positionForm.takeProfit"
            :precision="2"
            :step="0.01"
            :min="0"
            style="width: 100%"
          />
        </el-form-item>
        
        <el-form-item v-if="dialogType === 'create'" label="账户" prop="accountId">
          <el-select
            v-model="positionForm.accountId"
            placeholder="选择账户"
          >
            <el-option
              v-for="item in accountOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        
        <el-form-item v-if="dialogType === 'create'" label="策略" prop="strategyId">
          <el-select
            v-model="positionForm.strategyId"
            placeholder="选择策略"
            clearable
          >
            <el-option
              v-for="item in strategyOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
          <div class="form-help-text">不选择策略则为手动交易</div>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="positionDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitLoading" @click="submitPositionForm">
            {{ dialogType === 'create' ? '创建' : '保存' }}
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Position Detail Dialog -->
    <el-dialog
      v-model="detailDialogVisible"
      title="持仓详情"
      width="800px"
      destroy-on-close
    >
      <div v-if="currentPosition" class="position-detail-dialog">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="交易对">{{ currentPosition.symbol }}</el-descriptions-item>
          <el-descriptions-item label="方向">
            <el-tag :type="currentPosition.direction === 'long' ? 'success' : 'danger'">
              {{ currentPosition.direction === 'long' ? '多' : '空' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="杠杆">{{ currentPosition.leverage }}x</el-descriptions-item>
          <el-descriptions-item label="开仓价格">{{ formatCurrency(currentPosition.entryPrice) }}</el-descriptions-item>
          <el-descriptions-item label="当前价格">{{ formatCurrency(currentPosition.currentPrice) }}</el-descriptions-item>
          <el-descriptions-item label="数量">{{ formatNumber(currentPosition.amount) }}</el-descriptions-item>
          <el-descriptions-item label="保证金">{{ formatCurrency(currentPosition.margin) }}</el-descriptions-item>
          <el-descriptions-item label="未实现盈亏">
            <span :class="{ 'profit': currentPosition.unrealizedPnl > 0, 'loss': currentPosition.unrealizedPnl < 0 }">
              {{ formatCurrency(currentPosition.unrealizedPnl) }}
              ({{ formatPercentage(currentPosition.unrealizedPnlPercentage) }})
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(currentPosition.createdAt) }}</el-descriptions-item>
          <el-descriptions-item label="止损价格">
            {{ currentPosition.stopLoss ? formatCurrency(currentPosition.stopLoss) : '未设置' }}
          </el-descriptions-item>
          <el-descriptions-item label="止盈价格">
            {{ currentPosition.takeProfit ? formatCurrency(currentPosition.takeProfit) : '未设置' }}
          </el-descriptions-item>
          <el-descriptions-item label="强平价格">{{ formatCurrency(currentPosition.liquidationPrice) }}</el-descriptions-item>
          <el-descriptions-item label="账户">{{ currentPosition.accountName }}</el-descriptions-item>
          <el-descriptions-item label="策略">{{ currentPosition.strategyName || '手动' }}</el-descriptions-item>
        </el-descriptions>
        
        <div class="position-detail-charts">
          <h3>价格走势</h3>
          <div ref="detailChartRef" class="detail-chart"></div>
        </div>
        
        <div class="position-detail-history">
          <h3>操作历史</h3>
          <el-table
            :data="positionActionHistory"
            style="width: 100%"
            border
            size="small"
          >
            <el-table-column prop="time" label="时间" width="160">
              <template #default="scope">
                {{ formatDateTime(scope.row.time) }}
              </template>
            </el-table-column>
            <el-table-column prop="action" label="操作" width="120">
              <template #default="scope">
                <el-tag :type="getActionTagType(scope.row.action)">
                  {{ getActionText(scope.row.action) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="price" label="价格" width="120">
              <template #default="scope">
                {{ formatCurrency(scope.row.price) }}
              </template>
            </el-table-column>
            <el-table-column prop="amount" label="数量" width="120">
              <template #default="scope">
                {{ formatNumber(scope.row.amount) }}
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" />
          </el-table>
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
        
        <h3>自动刷新间隔</h3>
        <el-slider
          v-model="refreshInterval"
          :min="5"
          :max="60"
          :step="5"
          :marks="{5: '5秒', 15: '15秒', 30: '30秒', 60: '60秒'}"
        />
      </div>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showTableSettings = false">取消</el-button>
          <el-button type="primary" @click="saveTableSettings">保存</el-button>
          <el-button type="info" @click="resetTableSettings">重置默认</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Batch Close Dialog -->
    <el-dialog
      v-model="batchCloseDialogVisible"
      title="批量平仓"
      width="500px"
    >
      <div class="batch-close-dialog">
        <p>您确定要平仓以下 {{ selectedPositions.length }} 个持仓吗？</p>
        <el-table
          :data="selectedPositions"
          style="width: 100%"
          size="small"
        >
          <el-table-column prop="symbol" label="交易对" width="120" />
          <el-table-column prop="direction" label="方向" width="80">
            <template #default="scope">
              <el-tag
                :type="scope.row.direction === 'long' ? 'success' : 'danger'"
                size="small"
              >
                {{ scope.row.direction === 'long' ? '多' : '空' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="unrealizedPnl" label="未实现盈亏">
            <template #default="scope">
              <span 
                :class="{
                  'profit': scope.row.unrealizedPnl > 0,
                  'loss': scope.row.unrealizedPnl < 0
                }"
              >
                {{ formatCurrency(scope.row.unrealizedPnl) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        
        <div class="batch-close-summary">
          <div class="summary-item">
            <span>总计:</span>
            <span 
              :class="{
                'profit': batchPnlTotal > 0,
                'loss': batchPnlTotal < 0
              }"
            >
              {{ formatCurrency(batchPnlTotal) }}
            </span>
          </div>
        </div>
      </div>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="batchCloseDialogVisible = false">取消</el-button>
          <el-button type="danger" :loading="batchCloseLoading" @click="executeBatchClose">
            确认平仓
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Add to Position Dialog -->
    <el-dialog
      v-model="addPositionDialogVisible"
      title="加仓"
      width="400px"
    >
      <el-form
        ref="addPositionFormRef"
        :model="addPositionForm"
        :rules="addPositionRules"
        label-width="100px"
      >
        <el-form-item label="交易对">
          <el-input :model-value="currentPosition?.symbol" disabled />
        </el-form-item>
        
        <el-form-item label="方向">
          <el-tag :type="currentPosition?.direction === 'long' ? 'success' : 'danger'">
            {{ currentPosition?.direction === 'long' ? '多' : '空' }}
          </el-tag>
        </el-form-item>
        
        <el-form-item label="当前价格">
          <el-input :model-value="formatCurrency(currentPosition?.currentPrice)" disabled />
        </el-form-item>
        
        <el-form-item label="加仓数量" prop="amount">
          <el-input-number
            v-model="addPositionForm.amount"
            :precision="4"
            :step="0.01"
            :min="0.0001"
            style="width: 100%"
          />
        </el-form-item>
        
        <el-form-item label="价格类型" prop="priceType">
          <el-radio-group v-model="addPositionForm.priceType">
            <el-radio label="market">市价</el-radio>
            <el-radio label="limit">限价</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item v-if="addPositionForm.priceType === 'limit'" label="限价" prop="price">
          <el-input-number
            v-model="addPositionForm.price"
            :precision="2"
            :step="0.01"
            :min="0"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="addPositionDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitLoading" @click="submitAddPosition">
            确认加仓
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Reduce Position Dialog -->
    <el-dialog
      v-model="reducePositionDialogVisible"
      title="减仓"
      width="400px"
    >
      <el-form
        ref="reducePositionFormRef"
        :model="reducePositionForm"
        :rules="reducePositionRules"
        label-width="100px"
      >
        <el-form-item label="交易对">
          <el-input :model-value="currentPosition?.symbol" disabled />
        </el-form-item>
        
        <el-form-item label="方向">
          <el-tag :type="currentPosition?.direction === 'long' ? 'success' : 'danger'">
            {{ currentPosition?.direction === 'long' ? '多' : '空' }}
          </el-tag>
        </el-form-item>
        
        <el-form-item label="当前数量">
          <el-input :model-value="formatNumber(currentPosition?.amount)" disabled />
        </el-form-item>
        
        <el-form-item label="减仓比例" prop="percentage">
          <el-slider
            v-model="reducePositionForm.percentage"
            :min="1"
            :max="100"
            :step="1"
            :marks="{1: '1%', 25: '25%', 50: '50%', 75: '75%', 100: '100%'}"
          />
        </el-form-item>
        
        <el-form-item label="减仓数量" prop="amount">
          <el-input-number
            v-model="reducePositionForm.amount"
            :precision="4"
            :step="0.01"
            :min="0.0001"
            :max="currentPosition?.amount"
            style="width: 100%"
          />
        </el-form-item>
        
        <el-form-item label="价格类型" prop="priceType">
          <el-radio-group v-model="reducePositionForm.priceType">
            <el-radio label="market">市价</el-radio>
            <el-radio label="limit">限价</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item v-if="reducePositionForm.priceType === 'limit'" label="限价" prop="price">
          <el-input-number
            v-model="reducePositionForm.price"
            :precision="2"
            :step="0.01"
            :min="0"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="reducePositionDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitLoading" @click="submitReducePosition">
            确认减仓
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { ElMessage, ElMessageBox, FormInstance, FormRules } from 'element-plus'
import * as echarts from 'echarts'
import { format, parseISO, formatDistance } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import { 
  Position, 
  ArrowDown, 
  ArrowUp, 
  Refresh, 
  Plus, 
  Delete, 
  Download, 
  Search,
  Setting, 
  Edit, 
  View, 
  Close, 
  Remove, 
  Document,
  CaretTop, 
  CaretBottom 
} from '@element-plus/icons-vue'
import { 
  getActivePositions, 
  getPositionHistory,
  getPositionAnalytics,
  getPositionDetail,
  createPosition,
  updatePosition,
  closePosition,
  batchClosePositions,
  addToPosition,
  reducePosition
} from '@/api/trading'
import CryptoIcon from '@/components/CryptoIcon/index.vue'
import { exportToExcel, exportToCsv, exportToJson } from '@/utils/export'

// WebSocket connection
const { connect, disconnect, connected, lastMessage } = useWebSocket()

// State variables
const loading = ref(false)
const historyLoading = ref(false)
const analyticsLoading = ref(false)
const submitLoading = ref(false)
const batchCloseLoading = ref(false)
const advancedSearchVisible = ref(false)
const positionDialogVisible = ref(false)
const detailDialogVisible = ref(false)
const showTableSettings = ref(false)
const batchCloseDialogVisible = ref(false)
const addPositionDialogVisible = ref(false)
const reducePositionDialogVisible = ref(false)
const autoRefresh = ref(true)
const refreshInterval = ref(15) // seconds
const refreshTimer = ref<number | null>(null)
const dialogType = ref<'create' | 'edit'>('create')
const currentPosition = ref<any>(null)
const selectedPositions = ref<any[]>([])
const positionsTableRef = ref<any>(null)
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const historyCurrentPage = ref(1)
const historyPageSize = ref(10)
const totalPositionsCount = ref(0)
const totalHistoryCount = ref(0)
const analyticsTimeRange = ref('30d')
const historyDateRange = ref<[string, string]>([
  format(new Date(Date.now() - 30 * 24 * 60 * 60 * 1000), 'yyyy-MM-dd'),
  format(new Date(), 'yyyy-MM-dd')
])

// Chart references
let pnlTrendChart: echarts.ECharts | null = null
let positionDistributionChart: echarts.ECharts | null = null
let detailChart: echarts.ECharts | null = null
const pnlTrendChartRef = ref<HTMLElement | null>(null)
const positionDistributionChartRef = ref<HTMLElement | null>(null)
const detailChartRef = ref<HTMLElement | null>(null)

// Data
const positions = ref<any[]>([])
const positionHistory = ref<any[]>([])
const positionActionHistory = ref<any[]>([])
const analytics = reactive({
  winRate: 0,
  avgHoldingTime: '',
  profitLossRatio: 0,
  maxProfit: 0,
  maxLoss: 0,
  avgLeverage: 0,
  tradeFrequency: 0,
  maxDrawdown: 0,
  pnlTrend: [] as any[],
  distribution: [] as any[]
})

// Filter form
const filterForm = reactive({
  symbol: '',
  direction: '',
  strategy: '',
  pnlStatus: '',
  riskLevel: ''
})

// Advanced filter form
const advancedFilterForm = reactive({
  holdingTime: '',
  leverageRange: [1, 125],
  pnlRange: [-100, 100],
  dateRange: [] as string[],
  account: ''
})

// Position form
const positionForm = reactive({
  symbol: '',
  direction: 'long',
  priceType: 'market',
  price: 0,
  amount: 0,
  leverage: 10,
  stopLoss: null as number | null,
  takeProfit: null as number | null,
  accountId: '',
  strategyId: ''
})

// Add position form
const addPositionForm = reactive({
  priceType: 'market',
  price: 0,
  amount: 0
})

// Reduce position form
const reducePositionForm = reactive({
  priceType: 'market',
  price: 0,
  amount: 0,
  percentage: 50
})

// Form rules
const positionRules = reactive<FormRules>({
  symbol: [
    { required: true, message: '请选择交易对', trigger: 'change' }
  ],
  direction: [
    { required: true, message: '请选择方向', trigger: 'change' }
  ],
  amount: [
    { required: true, message: '请输入数量', trigger: 'blur' },
    { type: 'number', min: 0.0001, message: '数量必须大于0', trigger: 'blur' }
  ],
  price: [
    { required: true, message: '请输入价格', trigger: 'blur' },
    { type: 'number', min: 0.0001, message: '价格必须大于0', trigger: 'blur' }
  ],
  leverage: [
    { required: true, message: '请设置杠杆', trigger: 'change' },
    { type: 'number', min: 1, max: 125, message: '杠杆必须在1-125之间', trigger: 'blur' }
  ],
  accountId: [
    { required: true, message: '请选择账户', trigger: 'change' }
  ]
})

// Add position form rules
const addPositionRules = reactive<FormRules>({
  amount: [
    { required: true, message: '请输入加仓数量', trigger: 'blur' },
    { type: 'number', min: 0.0001, message: '数量必须大于0', trigger: 'blur' }
  ],
  price: [
    { required: true, message: '请输入价格', trigger: 'blur' },
    { type: 'number', min: 0.0001, message: '价格必须大于0', trigger: 'blur' }
  ]
})

// Reduce position form rules
const reducePositionRules = reactive<FormRules>({
  amount: [
    { required: true, message: '请输入减仓数量', trigger: 'blur' },
    { type: 'number', min: 0.0001, message: '数量必须大于0', trigger: 'blur' }
  ],
  percentage: [
    { required: true, message: '请选择减仓比例', trigger: 'change' },
    { type: 'number', min: 1, max: 100, message: '比例必须在1-100之间', trigger: 'blur' }
  ],
  price: [
    { required: true, message: '请输入价格', trigger: 'blur' },
    { type: 'number', min: 0.0001, message: '价格必须大于0', trigger: 'blur' }
  ]
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
  { prop: 'currentPrice', label: '当前价', width: 120 },
  { prop: 'amount', label: '数量', width: 120 },
  { prop: 'leverage', label: '杠杆', width: 80 },
  { prop: 'margin', label: '保证金', width: 120 },
  { prop: 'unrealizedPnl', label: '未实现盈亏', width: 150 },
  { prop: 'stopLoss', label: '止损', width: 120 },
  { prop: 'takeProfit', label: '止盈', width: 120 },
  { prop: 'riskLevel', label: '风险', width: 100 }
]

const visibleColumns = ref(allColumns.map(col => col.prop))

// Computed properties
const filteredPositions = computed(() => {
  let result = [...positions.value]
  
  // Apply filters
  if (filterForm.symbol) {
    result = result.filter(p => p.symbol === filterForm.symbol)
  }
  
  if (filterForm.direction) {
    result = result.filter(p => p.direction === filterForm.direction)
  }
  
  if (filterForm.strategy) {
    result = result.filter(p => p.strategyId === filterForm.strategy)
  }
  
  if (filterForm.pnlStatus) {
    if (filterForm.pnlStatus === 'profit') {
      result = result.filter(p => p.unrealizedPnl > 0)
    } else if (filterForm.pnlStatus === 'loss') {
      result = result.filter(p => p.unrealizedPnl < 0)
    }
  }
  
  if (filterForm.riskLevel) {
    result = result.filter(p => p.riskLevel === filterForm.riskLevel)
  }
  
  // Apply advanced filters
  if (advancedFilterForm.holdingTime) {
    const now = new Date()
    
    switch (advancedFilterForm.holdingTime) {
      case 'lt_1h':
        result = result.filter(p => {
          const created = new Date(p.createdAt)
          return (now.getTime() - created.getTime()) < 60 * 60 * 1000
        })
        break
      case '1h_24h':
        result = result.filter(p => {
          const created = new Date(p.createdAt)
          const diff = now.getTime() - created.getTime()
          return diff >= 60 * 60 * 1000 && diff < 24 * 60 * 60 * 1000
        })
        break
      case '1d_7d':
        result = result.filter(p => {
          const created = new Date(p.createdAt)
          const diff = now.getTime() - created.getTime()
          return diff >= 24 * 60 * 60 * 1000 && diff < 7 * 24 * 60 * 60 * 1000
        })
        break
      case 'gt_7d':
        result = result.filter(p => {
          const created = new Date(p.createdAt)
          return (now.getTime() - created.getTime()) >= 7 * 24 * 60 * 60 * 1000
        })
        break
    }
  }
  
  if (advancedFilterForm.leverageRange && advancedFilterForm.leverageRange.length === 2) {
    const [min, max] = advancedFilterForm.leverageRange
    result = result.filter(p => p.leverage >= min && p.leverage <= max)
  }
  
  if (advancedFilterForm.pnlRange && advancedFilterForm.pnlRange.length === 2) {
    const [min, max] = advancedFilterForm.pnlRange
    result = result.filter(p => {
      const pnlPercentage = p.unrealizedPnlPercentage
      return pnlPercentage >= min && pnlPercentage <= max
    })
  }
  
  if (advancedFilterForm.dateRange && advancedFilterForm.dateRange.length === 2) {
    const [startDate, endDate] = advancedFilterForm.dateRange
    const start = new Date(startDate)
    const end = new Date(endDate)
    end.setHours(23, 59, 59, 999) // End of the day
    
    result = result.filter(p => {
      const created = new Date(p.createdAt)
      return created >= start && created <= end
    })
  }
  
  if (advancedFilterForm.account) {
    result = result.filter(p => p.accountId === advancedFilterForm.account)
  }
  
  // Apply search keyword
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(p => 
      p.symbol.toLowerCase().includes(keyword) ||
      p.accountName?.toLowerCase().includes(keyword) ||
      p.strategyName?.toLowerCase().includes(keyword)
    )
  }
  
  return result
})

const totalPositions = computed(() => positions.value.length)
const longPositions = computed(() => positions.value.filter(p => p.direction === 'long').length)
const shortPositions = computed(() => positions.value.filter(p => p.direction === 'short').length)
const totalPositionValue = computed(() => {
  return positions.value.reduce((sum, p) => sum + p.amount * p.currentPrice, 0)
})
const totalPositionRatio = computed(() => {
  // Assume total account value is 100,000 USDT for now
  // In a real application, this would come from account balance data
  const totalAccountValue = 100000
  return ((totalPositionValue.value / totalAccountValue) * 100).toFixed(2)
})
const totalUnrealizedPnl = computed(() => {
  return positions.value.reduce((sum, p) => sum + p.unrealizedPnl, 0)
})
const totalUnrealizedPnlPercentage = computed(() => {
  const totalMargin = positions.value.reduce((sum, p) => sum + p.margin, 0)
  if (totalMargin === 0) return 0
  return (totalUnrealizedPnl.value / totalMargin) * 100
})
const riskPercentage = computed(() => {
  // Calculate risk percentage based on leverage, unrealized PnL, etc.
  // This is a simplified example - in a real application, you'd use a more sophisticated risk model
  const avgLeverage = positions.value.reduce((sum, p) => sum + p.leverage, 0) / Math.max(1, positions.value.length)
  const pnlRatio = totalUnrealizedPnl.value < 0 ? Math.abs(totalUnrealizedPnlPercentage.value) / 20 : 0
  const leverageRatio = avgLeverage / 125
  
  return Math.min(100, Math.round((leverageRatio * 60 + pnlRatio * 40)))
})
const riskLevel = computed(() => {
  if (riskPercentage.value < 30) return '低风险'
  if (riskPercentage.value < 70) return '中风险'
  return '高风险'
})
const riskColor = computed(() => {
  if (riskPercentage.value < 30) return '#67c23a'
  if (riskPercentage.value < 70) return '#e6a23c'
  return '#f56c6c'
})
const maxDrawdown = computed(() => {
  // In a real application, this would be calculated from historical data
  return 15.5
})
const hasSelectedPositions = computed(() => selectedPositions.value.length > 0)
const batchPnlTotal = computed(() => {
  return selectedPositions.value.reduce((sum, p) => sum + p.unrealizedPnl, 0)
})

// Watch for changes in reduce position percentage
watch(() => reducePositionForm.percentage, (newVal) => {
  if (currentPosition.value) {
    reducePositionForm.amount = parseFloat((currentPosition.value.amount * newVal / 100).toFixed(4))
  }
})

// Watch for changes in reduce position amount
watch(() => reducePositionForm.amount, (newVal) => {
  if (currentPosition.value && currentPosition.value.amount > 0) {
    reducePositionForm.percentage = Math.round((newVal / currentPosition.value.amount) * 100)
  }
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

const calculateHoldingTime = (dateStr: string) => {
  if (!dateStr) return ''
  try {
    const date = typeof dateStr === 'string' ? parseISO(dateStr) : new Date(dateStr)
    return formatDistance(date, new Date(), { addSuffix: false, locale: zhCN })
  } catch (e) {
    return ''
  }
}

const calculateLiquidationDistance = (position: any) => {
  if (!position || !position.liquidationPrice || !position.currentPrice) return 0
  
  const direction = position.direction
  const currentPrice = position.currentPrice
  const liquidationPrice = position.liquidationPrice
  
  if (direction === 'long') {
    return ((currentPrice - liquidationPrice) / currentPrice) * 100
  } else {
    return ((liquidationPrice - currentPrice) / currentPrice) * 100
  }
}

const getCryptoSymbol = (symbol: string) => {
  return symbol.split('-')[0].toLowerCase()
}

const getRiskTagType = (risk: string) => {
  switch (risk) {
    case 'low': return 'success'
    case 'medium': return 'warning'
    case 'high': return 'danger'
    default: return 'info'
  }
}

const getRiskLevelText = (risk: string) => {
  switch (risk) {
    case 'low': return '低风险'
    case 'medium': return '中风险'
    case 'high': return '高风险'
    default: return '未知'
  }
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

const getActionTagType = (action: string) => {
  switch (action) {
    case 'open': return 'success'
    case 'close': return 'danger'
    case 'add': return 'primary'
    case 'reduce': return 'warning'
    case 'update_sl': return 'info'
    case 'update_tp': return 'info'
    default: return 'info'
  }
}

const getActionText = (action: string) => {
  switch (action) {
    case 'open': return '开仓'
    case 'close': return '平仓'
    case 'add': return '加仓'
    case 'reduce': return '减仓'
    case 'update_sl': return '更新止损'
    case 'update_tp': return '更新止盈'
    default: return action
  }
}

// Data loading functions
const refreshPositions = async () => {
  try {
    loading.value = true
    
    const { data } = await getActivePositions({
      page: currentPage.value,
      limit: pageSize.value
    })
    
    positions.value = data.positions || []
    totalPositionsCount.value = data.total || 0
    
    // Initialize position charts after data is loaded
    nextTick(() => {
      positions.value.forEach(position => {
        if (position.pnlHistory) {
          initPositionPnlChart(position)
        }
      })
    })
    
    ElMessage.success('持仓数据已刷新')
  } catch (err) {
    console.error('加载持仓数据失败:', err)
    ElMessage.error('加载持仓数据失败')
  } finally {
    loading.value = false
  }
}

const loadPositionHistory = async () => {
  try {
    historyLoading.value = true
    
    const [startDate, endDate] = historyDateRange.value
    
    const { data } = await getPositionHistory({
      startDate,
      endDate,
      page: historyCurrentPage.value,
      limit: historyPageSize.value
    })
    
    positionHistory.value = data.positions || []
    totalHistoryCount.value = data.total || 0
  } catch (err) {
    console.error('加载持仓历史失败:', err)
    ElMessage.error('加载持仓历史失败')
  } finally {
    historyLoading.value = false
  }
}

const updateAnaly