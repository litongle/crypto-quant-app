<template>
  <div class="orders-container">
    <!-- Page header with title and actions -->
    <div class="page-header">
      <div class="header-title">
        <el-icon><Tickets /></el-icon>
        <h2>订单管理</h2>
      </div>
      <div class="header-actions">
        <el-button-group>
          <el-button
            type="primary"
            :icon="Refresh"
            :loading="loading"
            @click="refreshOrders"
          >
            刷新
          </el-button>
          <el-button
            type="success"
            :icon="Plus"
            @click="openCreateOrderDialog"
          >
            新建订单
          </el-button>
          <el-button
            type="danger"
            :icon="Delete"
            :disabled="!hasSelectedOrders"
            @click="confirmBatchCancel"
          >
            批量取消
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
              v-model="filterForm.side"
              placeholder="选择方向"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="买入" value="buy" />
              <el-option label="卖出" value="sell" />
            </el-select>
          </el-form-item>
          
          <el-form-item label="订单类型">
            <el-select
              v-model="filterForm.type"
              placeholder="选择类型"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="市价单" value="market" />
              <el-option label="限价单" value="limit" />
              <el-option label="止损单" value="stop" />
              <el-option label="跟踪止损" value="trailing_stop" />
            </el-select>
          </el-form-item>
          
          <el-form-item label="状态">
            <el-select
              v-model="filterForm.status"
              placeholder="选择状态"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="等待中" value="pending" />
              <el-option label="已成交" value="filled" />
              <el-option label="部分成交" value="partially_filled" />
              <el-option label="已取消" value="cancelled" />
              <el-option label="已拒绝" value="rejected" />
              <el-option label="已过期" value="expired" />
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
          
          <el-form-item label="价格范围">
            <el-input-number
              v-model="advancedFilterForm.minPrice"
              placeholder="最低价"
              :precision="2"
              :step="0.01"
              :min="0"
              style="width: 130px"
              @change="handleFilterChange"
            />
            <span class="range-separator">至</span>
            <el-input-number
              v-model="advancedFilterForm.maxPrice"
              placeholder="最高价"
              :precision="2"
              :step="0.01"
              :min="0"
              style="width: 130px"
              @change="handleFilterChange"
            />
          </el-form-item>
          
          <el-form-item label="数量范围">
            <el-input-number
              v-model="advancedFilterForm.minAmount"
              placeholder="最小数量"
              :precision="4"
              :step="0.01"
              :min="0"
              style="width: 130px"
              @change="handleFilterChange"
            />
            <span class="range-separator">至</span>
            <el-input-number
              v-model="advancedFilterForm.maxAmount"
              placeholder="最大数量"
              :precision="4"
              :step="0.01"
              :min="0"
              style="width: 130px"
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
          
          <el-form-item label="来源">
            <el-select
              v-model="advancedFilterForm.source"
              placeholder="订单来源"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="手动" value="manual" />
              <el-option label="策略" value="strategy" />
              <el-option label="API" value="api" />
              <el-option label="止盈止损" value="tp_sl" />
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
            <div class="statistic-title">活跃订单</div>
            <div class="statistic-value">{{ activeOrdersCount }}</div>
            <div class="statistic-footer">
              <span>买入: {{ buyOrdersCount }}</span>
              <span>卖出: {{ sellOrdersCount }}</span>
            </div>
          </el-card>
        </el-col>
        
        <el-col :xs="24" :sm="12" :md="6">
          <el-card shadow="hover" class="statistic-card">
            <div class="statistic-title">今日成交</div>
            <div class="statistic-value">{{ todayFilledOrdersCount }}</div>
            <div class="statistic-footer">
              <span>成交金额: {{ formatCurrency(todayFilledVolume) }}</span>
            </div>
          </el-card>
        </el-col>
        
        <el-col :xs="24" :sm="12" :md="6">
          <el-card shadow="hover" class="statistic-card">
            <div class="statistic-title">成交率</div>
            <div class="statistic-value">{{ formatPercentage(fillRate) }}</div>
            <div class="statistic-footer">
              <el-progress :percentage="fillRate" :stroke-width="5" :show-text="false" />
            </div>
          </el-card>
        </el-col>
        
        <el-col :xs="24" :sm="12" :md="6">
          <el-card shadow="hover" class="statistic-card">
            <div class="statistic-title">平均成交时间</div>
            <div class="statistic-value">{{ avgFillTime }}</div>
            <div class="statistic-footer">
              <span>最快: {{ fastestFillTime }}</span>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- Order book preview -->
    <el-card v-if="showOrderBook" shadow="never" class="order-book-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>实时订单簿 - {{ currentSymbol }}</span>
          </div>
          <div class="header-right">
            <el-select
              v-model="currentSymbol"
              placeholder="选择交易对"
              size="small"
              @change="changeOrderBookSymbol"
            >
              <el-option
                v-for="item in symbolOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
            <el-button :icon="Close" circle size="small" @click="showOrderBook = false" />
          </div>
        </div>
      </template>
      
      <div class="order-book-container">
        <div class="order-book-asks">
          <div class="order-book-header">卖单</div>
          <div class="order-book-list">
            <div 
              v-for="(ask, index) in orderBookData.asks" 
              :key="'ask-' + index" 
              class="order-book-item"
            >
              <div class="price sell">{{ formatCurrency(ask.price) }}</div>
              <div class="amount">{{ formatNumber(ask.amount) }}</div>
              <div class="total">{{ formatNumber(ask.total) }}</div>
              <div class="depth-bar sell" :style="{ width: ask.percentage + '%' }"></div>
            </div>
          </div>
        </div>
        
        <div class="order-book-spread">
          <div class="spread-price">
            <span>价差:</span>
            <span>{{ formatCurrency(orderBookSpread) }} ({{ formatPercentage(orderBookSpreadPercentage) }})</span>
          </div>
        </div>
        
        <div class="order-book-bids">
          <div class="order-book-header">买单</div>
          <div class="order-book-list">
            <div 
              v-for="(bid, index) in orderBookData.bids" 
              :key="'bid-' + index" 
              class="order-book-item"
            >
              <div class="price buy">{{ formatCurrency(bid.price) }}</div>
              <div class="amount">{{ formatNumber(bid.amount) }}</div>
              <div class="total">{{ formatNumber(bid.total) }}</div>
              <div class="depth-bar buy" :style="{ width: bid.percentage + '%' }"></div>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- Active orders table -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>活跃订单</span>
            <el-tag type="info" size="small">{{ filteredActiveOrders.length }}</el-tag>
          </div>
          <div class="header-right">
            <el-button 
              type="primary" 
              plain 
              size="small" 
              :icon="Menu" 
              @click="showOrderBook = !showOrderBook"
            >
              {{ showOrderBook ? '隐藏订单簿' : '显示订单簿' }}
            </el-button>
            <el-input
              v-model="searchKeyword"
              placeholder="搜索订单..."
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
        <span>加载订单数据...</span>
      </div>
      
      <!-- Empty state -->
      <el-empty
        v-else-if="filteredActiveOrders.length === 0"
        description="暂无活跃订单"
      >
        <template #image>
          <el-icon class="empty-icon"><Document /></el-icon>
        </template>
        <el-button type="primary" @click="openCreateOrderDialog">创建订单</el-button>
      </el-empty>
      
      <!-- Active orders table -->
      <el-table
        v-else
        ref="ordersTableRef"
        :data="filteredActiveOrders"
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
            <div class="order-detail">
              <el-descriptions :column="3" border>
                <el-descriptions-item label="订单ID">{{ props.row.orderId }}</el-descriptions-item>
                <el-descriptions-item label="客户端ID">{{ props.row.clientOrderId }}</el-descriptions-item>
                <el-descriptions-item label="创建时间">
                  {{ formatDateTime(props.row.createdAt) }}
                </el-descriptions-item>
                <el-descriptions-item label="更新时间">
                  {{ formatDateTime(props.row.updatedAt) }}
                </el-descriptions-item>
                <el-descriptions-item label="账户">
                  {{ props.row.accountName }}
                </el-descriptions-item>
                <el-descriptions-item label="来源">
                  {{ getOrderSourceText(props.row.source) }}
                </el-descriptions-item>
                <el-descriptions-item label="杠杆">
                  {{ props.row.leverage }}x
                </el-descriptions-item>
                <el-descriptions-item label="保证金">
                  {{ formatCurrency(props.row.margin) }}
                </el-descriptions-item>
                <el-descriptions-item label="手续费">
                  {{ formatCurrency(props.row.fee) }}
                </el-descriptions-item>
                <el-descriptions-item v-if="props.row.triggerPrice" label="触发价格">
                  {{ formatCurrency(props.row.triggerPrice) }}
                </el-descriptions-item>
                <el-descriptions-item v-if="props.row.trailingDistance" label="追踪距离">
                  {{ formatCurrency(props.row.trailingDistance) }}
                </el-descriptions-item>
                <el-descriptions-item v-if="props.row.timeInForce" label="有效期">
                  {{ getTimeInForceText(props.row.timeInForce) }}
                </el-descriptions-item>
                <el-descriptions-item v-if="props.row.postOnly" label="只做挂单">
                  {{ props.row.postOnly ? '是' : '否' }}
                </el-descriptions-item>
                <el-descriptions-item v-if="props.row.reduceOnly" label="只减仓">
                  {{ props.row.reduceOnly ? '是' : '否' }}
                </el-descriptions-item>
              </el-descriptions>
              
              <div class="order-actions">
                <el-button-group>
                  <el-button 
                    type="primary" 
                    :icon="Edit"
                    @click.stop="editOrder(props.row)"
                    :disabled="!canEditOrder(props.row)"
                  >
                    编辑
                  </el-button>
                  <el-button 
                    type="danger" 
                    :icon="Close"
                    @click.stop="confirmCancelOrder(props.row)"
                    :disabled="!canCancelOrder(props.row)"
                  >
                    取消
                  </el-button>
                </el-button-group>
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
        
        <el-table-column prop="side" label="方向" width="80">
          <template #default="scope">
            <el-tag
              :type="scope.row.side === 'buy' ? 'success' : 'danger'"
              effect="plain"
            >
              {{ scope.row.side === 'buy' ? '买入' : '卖出' }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="type" label="类型" width="120">
          <template #default="scope">
            <el-tag :type="getOrderTypeTagType(scope.row.type)">
              {{ getOrderTypeText(scope.row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="price" label="价格" width="120" sortable>
          <template #default="scope">
            <span v-if="scope.row.type === 'market'">市价</span>
            <span v-else>{{ formatCurrency(scope.row.price) }}</span>
          </template>
        </el-table-column>
        
        <el-table-column prop="amount" label="数量" width="120" sortable>
          <template #default="scope">
            {{ formatNumber(scope.row.amount) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="filled" label="已成交" width="120" sortable>
          <template #default="scope">
            {{ formatNumber(scope.row.filled) }}
            <div class="fill-progress">
              <el-progress 
                :percentage="(scope.row.filled / scope.row.amount) * 100" 
                :stroke-width="4" 
                :show-text="false"
              />
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="status" label="状态" width="120">
          <template #default="scope">
            <el-tag :type="getOrderStatusTagType(scope.row.status)">
              {{ getOrderStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="createdAt" label="创建时间" width="180" sortable>
          <template #default="scope">
            {{ formatDateTime(scope.row.createdAt) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" fixed="right" width="150">
          <template #default="scope">
            <el-button-group>
              <el-tooltip content="编辑订单" placement="top" v-if="canEditOrder(scope.row)">
                <el-button 
                  type="primary" 
                  :icon="Edit" 
                  circle
                  size="small"
                  @click.stop="editOrder(scope.row)"
                />
              </el-tooltip>
              <el-tooltip content="查看详情" placement="top">
                <el-button 
                  type="info" 
                  :icon="View" 
                  circle
                  size="small"
                  @click.stop="viewOrderDetail(scope.row)"
                />
              </el-tooltip>
              <el-tooltip content="取消订单" placement="top" v-if="canCancelOrder(scope.row)">
                <el-button 
                  type="danger" 
                  :icon="Close" 
                  circle
                  size="small"
                  @click.stop="confirmCancelOrder(scope.row)"
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
          :total="totalActiveOrdersCount"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- Order History -->
    <el-card shadow="never" class="history-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>订单历史</span>
            <el-tag type="info" size="small">{{ orderHistory.length }}</el-tag>
          </div>
          <div class="header-right">
            <el-date-picker
              v-model="historyDateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
              @change="loadOrderHistory"
            />
          </div>
        </div>
      </template>
      
      <div v-if="historyLoading" class="loading-container">
        <el-spin class="loading-spinner" />
        <span>加载历史数据...</span>
      </div>
      
      <el-empty
        v-else-if="orderHistory.length === 0"
        description="暂无历史订单"
      />
      
      <el-table
        v-else
        :data="orderHistory"
        style="width: 100%"
        border
        stripe
        size="small"
      >
        <el-table-column prop="symbol" label="交易对" width="120" />
        <el-table-column prop="side" label="方向" width="80">
          <template #default="scope">
            <el-tag
              :type="scope.row.side === 'buy' ? 'success' : 'danger'"
              size="small"
              effect="plain"
            >
              {{ scope.row.side === 'buy' ? '买入' : '卖出' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="100">
          <template #default="scope">
            <el-tag :type="getOrderTypeTagType(scope.row.type)" size="small">
              {{ getOrderTypeText(scope.row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="price" label="价格" width="120">
          <template #default="scope">
            <span v-if="scope.row.type === 'market'">市价</span>
            <span v-else>{{ formatCurrency(scope.row.price) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="数量" width="120">
          <template #default="scope">
            {{ formatNumber(scope.row.amount) }}
          </template>
        </el-table-column>
        <el-table-column prop="filled" label="已成交" width="120">
          <template #default="scope">
            {{ formatNumber(scope.row.filled) }}
            <div class="fill-progress">
              <el-progress 
                :percentage="(scope.row.filled / scope.row.amount) * 100" 
                :stroke-width="4" 
                :show-text="false"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="avgFillPrice" label="成交均价" width="120">
          <template #default="scope">
            {{ scope.row.avgFillPrice ? formatCurrency(scope.row.avgFillPrice) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="getOrderStatusTagType(scope.row.status)" size="small">
              {{ getOrderStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" label="创建时间" width="160">
          <template #default="scope">
            {{ formatDateTime(scope.row.createdAt) }}
          </template>
        </el-table-column>
        <el-table-column prop="updatedAt" label="更新时间" width="160">
          <template #default="scope">
            {{ formatDateTime(scope.row.updatedAt) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="scope">
            <el-button
              type="info"
              :icon="View"
              circle
              size="small"
              @click.stop="viewOrderDetail(scope.row)"
            />
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

    <!-- Order Analytics -->
    <el-card shadow="never" class="analytics-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>订单分析</span>
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
            <div ref="orderVolumeChartContainer" class="chart-container">
              <h3>订单量趋势</h3>
              <div ref="orderVolumeChartRef" class="analytics-chart"></div>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div ref="orderTypeDistributionContainer" class="chart-container">
              <h3>订单类型分布</h3>
              <div ref="orderTypeDistributionChartRef" class="analytics-chart"></div>
            </div>
          </el-col>
        </el-row>
        <el-row :gutter="20" class="analytics-metrics">
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">总订单数</div>
              <div class="metric-value">{{ analytics.totalOrders }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">成交率</div>
              <div class="metric-value">{{ formatPercentage(analytics.fillRate) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">取消率</div>
              <div class="metric-value">{{ formatPercentage(analytics.cancelRate) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">平均成交时间</div>
              <div class="metric-value">{{ analytics.avgFillTime }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">买入订单</div>
              <div class="metric-value">{{ analytics.buyOrders }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">卖出订单</div>
              <div class="metric-value">{{ analytics.sellOrders }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">平均滑点</div>
              <div class="metric-value">{{ formatPercentage(analytics.avgSlippage) }}</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="8" :md="6">
            <div class="metric-card">
              <div class="metric-title">总手续费</div>
              <div class="metric-value">{{ formatCurrency(analytics.totalFees) }}</div>
            </div>
          </el-col>
        </el-row>
      </div>
    </el-card>

    <!-- Create/Edit Order Dialog -->
    <el-dialog
      v-model="orderDialogVisible"
      :title="dialogType === 'create' ? '新建订单' : '编辑订单'"
      width="600px"
      destroy-on-close
    >
      <el-form
        ref="orderFormRef"
        :model="orderForm"
        :rules="orderRules"
        label-width="100px"
      >
        <el-form-item label="交易对" prop="symbol">
          <el-select
            v-model="orderForm.symbol"
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
        
        <el-form-item label="方向" prop="side">
          <el-radio-group v-model="orderForm.side" :disabled="dialogType === 'edit'">
            <el-radio label="buy">买入</el-radio>
            <el-radio label="sell">卖出</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item label="订单类型" prop="type">
          <el-select
            v-model="orderForm.type"
            placeholder="选择订单类型"
            :disabled="dialogType === 'edit'"
          >
            <el-option label="市价单" value="market" />
            <el-option label="限价单" value="limit" />
            <el-option label="止损单" value="stop" />
            <el-option label="止损限价单" value="stop_limit" />
            <el-option label="跟踪止损" value="trailing_stop" />
          </el-select>
        </el-form-item>
        
        <el-form-item v-if="orderForm.type !== 'market'" label="价格" prop="price">
          <el-input-number
            v-model="orderForm.price"
            :precision="2"
            :step="0.01"
            :min="0"
            style="width: 100%"
          />
        </el-form-item>
        
        <el-form-item v-if="['stop', 'stop_limit'].includes(orderForm.type)" label="触发价格" prop="triggerPrice">
          <el-input-number
            v-model="orderForm.triggerPrice"
            :precision="2"
            :step="0.01"
            :min="0"
            style="width: 100%"
          />
        </el-form-item>
        
        <el-form-item v-if="orderForm.type === 'trailing_stop'" label="追踪距离" prop="trailingDistance">
          <el-input-number
            v-model="orderForm.trailingDistance"
            :precision="2"
            :step="0.01"
            :min="0"
            style="width: 100%"
          />
          <div class="form-help-text">价格变动多少触发订单（按金额）</div>
        </el-form-item>
        
        <el-form-item v-if="orderForm.type === 'trailing_stop'" label="追踪百分比" prop="trailingPercent">
          <el-slider
            v-model="orderForm.trailingPercent"
            :min="0.1"
            :max="5"
            :step="0.1"
            :marks="{0.1: '0.1%', 1: '1%', 2: '2%', 3: '3%', 4: '4%', 5: '5%'}"
          />
          <div class="form-help-text">价格变动百分比触发订单</div>
        </el-form-item>
        
        <el-form-item label="数量" prop="amount">
          <el-input-number
            v-model="orderForm.amount"
            :precision="4"
            :step="0.01"
            :min="0.0001"
            style="width: 100%"
          />
        </el-form-item>
        
        <el-form-item v-if="dialogType === 'create'" label="杠杆" prop="leverage">
          <el-slider
            v-model="orderForm.leverage"
            :min="1"
            :max="125"
            :step="1"
            :marks="{1: '1x', 25: '25x', 50: '50x', 75: '75x', 100: '100x', 125: '125x'}"
          />
        </el-form-item>
        
        <el-form-item label="有效期" prop="timeInForce">
          <el-select
            v-model="orderForm.timeInForce"
            placeholder="选择有效期"
          >
            <el-option label="GTC - 成交为止" value="GTC" />
            <el-option label="IOC - 立即成交或取消" value="IOC" />
            <el-option label="FOK - 全部成交或取消" value="FOK" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="高级选项">
          <div class="advanced-options">
            <el-checkbox v-model="orderForm.postOnly">只做挂单</el-checkbox>
            <el-tooltip content="订单将只作为挂单存在，不会立即成交" placement="top">
              <el-icon><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
          <div class="advanced-options">
            <el-checkbox v-model="orderForm.reduceOnly">只减仓</el-checkbox>
            <el-tooltip content="订单只会减少持仓，不会增加持仓" placement="top">
              <el-icon><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
        </el-form-item>
        
        <el-form-item v-if="dialogType === 'create'" label="账户" prop="accountId">
          <el-select
            v-model="orderForm.accountId"
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
      </el-form>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="orderDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitLoading" @click="submitOrderForm">
            {{ dialogType === 'create' ? '创建' : '保存' }}
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Order Detail Dialog -->
    <el-dialog
      v-model="detailDialogVisible"
      title="订单详情"
      width="800px"
      destroy-on-close
    >
      <div v-if="currentOrder" class="order-detail-dialog">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="订单ID">{{ currentOrder.orderId }}</el-descriptions-item>
          <el-descriptions-item label="交易对">{{ currentOrder.symbol }}</el-descriptions-item>
          <el-descriptions-item label="方向">
            <el-tag :type="currentOrder.side === 'buy' ? 'success' : 'danger'">
              {{ currentOrder.side === 'buy' ? '买入' : '卖出' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="类型">
            <el-tag :type="getOrderTypeTagType(currentOrder.type)">
              {{ getOrderTypeText(currentOrder.type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="价格">
            {{ currentOrder.type === 'market' ? '市价' : formatCurrency(currentOrder.price) }}
          </el-descriptions-item>
          <el-descriptions-item label="数量">{{ formatNumber(currentOrder.amount) }}</el-descriptions-item>
          <el-descriptions-item label="已成交数量">{{ formatNumber(currentOrder.filled) }}</el-descriptions-item>
          <el-descriptions-item label="成交均价">
            {{ currentOrder.avgFillPrice ? formatCurrency(currentOrder.avgFillPrice) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getOrderStatusTagType(currentOrder.status)">
              {{ getOrderStatusText(currentOrder.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(currentOrder.createdAt) }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ formatDateTime(currentOrder.updatedAt) }}</el-descriptions-item>
          <el-descriptions-item label="账户">{{ currentOrder.accountName }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ getOrderSourceText(currentOrder.source) }}</el-descriptions-item>
          <el-descriptions-item label="杠杆">{{ currentOrder.leverage }}x</el-descriptions-item>
          <el-descriptions-item label="手续费">{{ formatCurrency(currentOrder.fee) }}</el-descriptions-item>
          <el-descriptions-item v-if="currentOrder.triggerPrice" label="触发价格">
            {{ formatCurrency(currentOrder.triggerPrice) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="currentOrder.trailingDistance" label="追踪距离">
            {{ formatCurrency(currentOrder.trailingDistance) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="currentOrder.timeInForce" label="有效期">
            {{ getTimeInForceText(currentOrder.timeInForce) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="currentOrder.postOnly" label="只做挂单">
            {{ currentOrder.postOnly ? '是' : '否' }}
          </el-descriptions-item>
          <el-descriptions-item v-if="currentOrder.reduceOnly" label="只减仓">
            {{ currentOrder.reduceOnly ? '是' : '否' }}
          </el-descriptions-item>
        </el-descriptions>
        
        <div v-if="orderFillHistory.length > 0" class="order-fill-history">
          <h3>成交明细</h3>
          <el-table
            :data="orderFillHistory"
            style="width: 100%"
            border
            size="small"
          >
            <el-table-column prop="time" label="时间" width="160">
              <template #default="scope">
                {{ formatDateTime(scope.row.time) }}
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
            <el-table-column prop="fee" label="手续费" width="120">
              <template #default="scope">
                {{ formatCurrency(scope.row.fee) }}
              </template>
            </el-table-column>
            <el-table-column prop="liquidity" label="流动性" width="100">
              <template #default="scope">
                {{ scope.row.liquidity === 'maker' ? '挂单' : '吃单' }}
              </template>
            </el-table-column>
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

    <!-- Batch Cancel Dialog -->
    <el-dialog
      v-model="batchCancelDialogVisible"
      title="批量取消订单"
      width="500px"
    >
      <div class="batch-cancel-dialog">
        <p>您确定要取消以下 {{ selectedOrders.length }} 个订单吗？</p>
        <el-table
          :data="selectedOrders"
          style="width: 100%"
          size="small"
        >
          <el-table-column prop="symbol" label="交易对" width="120" />
          <el-table-column prop="side" label="方向" width="80">
            <template #default="scope">
              <el-tag
                :type="scope.row.side === 'buy' ? 'success' : 'danger'"
                size="small"
              >
                {{ scope.row.side === 'buy' ? '买入' : '卖出' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="type" label="类型" width="100">
            <template #default="scope">
              <el-tag :type="getOrderTypeTagType(scope.row.type)" size="small">
                {{ getOrderTypeText(scope.row.type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="price" label="价格" width="120">
            <template #default="scope">
              <span v-if="scope.row.type === 'market'">市价</span>
              <span v-else>{{ formatCurrency(scope.row.price) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="数量">
            <template #default="scope">
              {{ formatNumber(scope.row.amount) }}
            </template>
          </el-table-column>
        </el-table>
      </div>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="batchCancelDialogVisible = false">取消</el-button>
          <el-button type="danger" :loading="batchCancelLoading" @click="executeBatchCancel">
            确认取消
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
  Tickets, 
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
  Menu, 
  Document,
  QuestionFilled
} from '@element-plus/icons-vue'
import { 
  getActiveOrders, 
  getOrderHistory,
  getOrderAnalytics,
  getOrderDetail,
  createOrder,
  updateOrder,
  cancelOrder,
  batchCancelOrders,
  getOrderBook,
  getOrderFills
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
const batchCancelLoading = ref(false)
const advancedSearchVisible = ref(false)
const orderDialogVisible = ref(false)
const detailDialogVisible = ref(false)
const showTableSettings = ref(false)
const batchCancelDialogVisible = ref(false)
const showOrderBook = ref(false)
const autoRefresh = ref(true)
const refreshInterval = ref(15) // seconds
const refreshTimer = ref<number | null>(null)
const dialogType = ref<'create' | 'edit'>('create')
const currentOrder = ref<any>(null)
const selectedOrders = ref<any[]>([])
const ordersTableRef = ref<any>(null)
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const historyCurrentPage = ref(1)
const historyPageSize = ref(10)
const totalActiveOrdersCount = ref(0)
const totalHistoryCount = ref(0)
const analyticsTimeRange = ref('30d')
const currentSymbol = ref('ETH-USDT')
const historyDateRange = ref<[string, string]>([
  format(new Date(Date.now() - 30 * 24 * 60 * 60 * 1000), 'yyyy-MM-dd'),
  format(new Date(), 'yyyy-MM-dd')
])

// Chart references
let orderVolumeChart: echarts.ECharts | null = null
let orderTypeDistributionChart: echarts.ECharts | null = null
const orderVolumeChartRef = ref<HTMLElement | null>(null)
const orderTypeDistributionChartRef = ref<HTMLElement | null>(null)

// Data
const activeOrders = ref<any[]>([])
const orderHistory = ref<any[]>([])
const orderFillHistory = ref<any[]>([])
const orderBookData = reactive({
  asks: [] as any[],
  bids: [] as any[],
  timestamp: 0
})
const analytics = reactive({
  totalOrders: 0,
  fillRate: 0,
  cancelRate: 0,
  avgFillTime: '',
  buyOrders: 0,
  sellOrders: 0,
  avgSlippage: 0,
  totalFees: 0,
  volumeTrend: [] as any[],
  typeDistribution: [] as any[]
})

// Filter form
const filterForm = reactive({
  symbol: '',
  side: '',
  type: '',
  status: ''
})

// Advanced filter form
const advancedFilterForm = reactive({
  dateRange: [] as string[],
  minPrice: null as number | null,
  maxPrice: null as number | null,
  minAmount: null as number | null,
  maxAmount: null as number | null,
  account: '',
  source: ''
})

// Order form
const orderForm = reactive({
  symbol: '',
  side: 'buy',
  type: 'limit',
  price: 0,
  triggerPrice: null as number | null,
  trailingDistance: null as number | null,
  trailingPercent: 1,
  amount: 0,
  leverage: 10,
  timeInForce: 'GTC',
  postOnly: false,
  reduceOnly: false,
  accountId: ''
})

// Form rules
const orderRules = reactive<FormRules>({
  symbol: [
    { required: true, message: '请选择交易对', trigger: 'change' }
  ],
  side: [
    { required: true, message: '请选择方向', trigger: 'change' }
  ],
  type: [
    { required: true, message: '请选择订单类型', trigger: 'change' }
  ],
  price: [
    { required: true, message: '请输入价格', trigger: 'blur' },
    { type: 'number', min: 0.0001, message: '价格必须大于0', trigger: 'blur' }
  ],
  triggerPrice: [
    { required: true, message: '请输入触发价格', trigger: 'blur' },
    { type: 'number', min: 0.0001, message: '触发价格必须大于0', trigger: 'blur' }
  ],
  trailingDistance: [
    { required: true, message: '请输入追踪距离', trigger: 'blur' },
    { type: 'number', min: 0.0001, message: '追踪距离必须大于0', trigger: 'blur' }
  ],
  amount: [
    { required: true, message: '请输入数量', trigger: 'blur' },
    { type: 'number', min: 0.0001, message: '数量必须大于0', trigger: 'blur' }
  ],
  leverage: [
    { required: true, message: '请设置杠杆', trigger: 'change' },
    { type: 'number', min: 1, max: 125, message: '杠杆必须在1-125之间', trigger: 'blur' }
  ],
  accountId: [
    { required: true, message: '请选择账户', trigger: 'change' }
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

const accountOptions = [
  { label: 'OKX主账户', value: '1' },
  { label: 'OKX子账户1', value: '2' },
  { label: 'OKX子账户2', value: '3' },
  { label: 'Binance账户', value: '4' }
]

// Table columns
const allColumns = [
  { prop: 'symbol', label: '交易对', width: 120 },
  { prop: 'side', label: '方向', width: 80 },
  { prop: 'type', label: '类型', width: 120 },
  { prop: 'price', label: '价格', width: 120 },
  { prop: 'amount', label: '数量', width: 120 },
  { prop: 'filled', label: '已成交', width: 120 },
  { prop: 'status', label: '状态', width: 120 },
  { prop: 'createdAt', label: '创建时间', width: 180 }
]

const visibleColumns = ref(allColumns.map(col => col.prop))

// Computed properties
const filteredActiveOrders = computed(() => {
  let result = [...activeOrders.value]
  
  // Apply filters
  if (filterForm.symbol) {
    result = result.filter(p => p.symbol === filterForm.symbol)
  }
  
  if (filterForm.side) {
    result = result.filter(p => p.side === filterForm.side)
  }
  
  if (filterForm.type) {
    result = result.filter(p => p.type === filterForm.type)
  }
  
  if (filterForm.status) {
    result = result.filter(p => p.status === filterForm.status)
  }
  
  // Apply advanced filters
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
  
  if (advancedFilterForm.minPrice !== null) {
    result = result.filter(p => p.type !== 'market' && p.price >= advancedFilterForm.minPrice!)
  }
  
  if (advancedFilterForm.maxPrice !== null) {
    result = result.filter(p => p.type !== 'market' && p.price <= advancedFilterForm.maxPrice!)
  }
  
  if (advancedFilterForm.minAmount !== null) {
    result = result.filter(p => p.amount >= advancedFilterForm.minAmount!)
  }
  
  if (advancedFilterForm.maxAmount !== null) {
    result = result.filter(p => p.amount <= advancedFilterForm.maxAmount!)
  }
  
  if (advancedFilterForm.account) {
    result = result.filter(p => p.accountId === advancedFilterForm.account)
  }
  
  if (advancedFilterForm.source) {
    result = result.filter(p => p.source === advancedFilterForm.source)
  }
  
  // Apply search keyword
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(p => 
      p.symbol.toLowerCase().includes(keyword) ||
      p.orderId?.toLowerCase().includes(keyword) ||
      p.clientOrderId?.toLowerCase().includes(keyword) ||
      p.accountName?.toLowerCase().includes(keyword)
    )
  }
  
  return result
})

const activeOrdersCount = computed(() => activeOrders.value.length)
const buyOrdersCount = computed(() => activeOrders.value.filter(o => o.side === 'buy').length)
const sellOrdersCount = computed(() => activeOrders.value.filter(o => o.side === 'sell').length)
const todayFilledOrdersCount = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  
  return orderHistory.value.filter(o => {
    return o.status === 'filled' && new Date(o.updatedAt) >= today
  }).length
})
const todayFilledVolume = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  
  return orderHistory.value
    .filter(o => o.status === 'filled' && new Date(o.updatedAt) >= today)
    .reduce((sum, o) => sum + (o.filled * (o.avgFillPrice || o.price)), 0)
})
const fillRate = computed(() => {
  const totalOrders = orderHistory.value.length
  if (totalOrders === 0) return 0
  
  const filledOrders = orderHistory.value.filter(o => o.status === 'filled').length
  return (filledOrders / totalOrders) * 100
})
const avgFillTime = computed(() => {
  const filledOrders = orderHistory.value.filter(o => o.status === 'filled')
  if (filledOrders.length === 0) return '0分钟'
  
  const totalTime = filledOrders.reduce((sum, o) => {
    const created = new Date(o.createdAt).getTime()
    const updated = new Date(o.updatedAt).getTime()
    return sum + (updated - created)
  }, 0)
  
  const avgTimeMs = totalTime / filledOrders.length
  
  if (avgTimeMs < 60000) {
    return `${Math.round(avgTimeMs / 1000)}秒`
  } else if (avgTimeMs < 3600000) {
    return `${Math.round(avgTimeMs / 60000)}分钟`
  } else {
    return `${(avgTimeMs / 3600000).toFixed(1)}小时`
  }
})
const fastestFillTime = computed(() => {
  const filledOrders = orderHistory.value.filter(o => o.status === 'filled')
  if (filledOrders.length === 0) return '0秒'
  
  let fastest = Number.MAX_SAFE_INTEGER
  
  filledOrders.forEach(o => {
    const created = new Date(o.createdAt).getTime()
    const updated = new Date(o.updatedAt).getTime()
    const time = updated - created
    if (time < fastest) {
      fastest = time
    }
  })
  
  if (fastest < 60000) {
    return `${Math.round(fastest / 1000)}秒`
  } else {
    return `${Math.round(fastest / 60000)}分钟`
  }
})
const hasSelectedOrders = computed(() => selectedOrders.value.length > 0)
const orderBookSpread = computed(() => {
  if (orderBookData.asks.length === 0 || orderBookData.bids.length === 0) return 0
  
  const lowestAsk = orderBookData.asks[0].price
  const highestBid = orderBookData.bids[0].price
  
  return lowestAsk - highestBid
})
const orderBookSpreadPercentage = computed(() => {
  if (orderBookData.asks.length === 0 || orderBookData.bids.length === 0) return 0
  
  const lowestAsk = orderBookData.asks[0].price
  const highestBid = orderBookData.bids[0].price
  
  return ((lowestAsk - highestBid) / lowestAsk) * 100
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

const getOrderTypeTagType = (type: string) => {
  switch (type) {
    case 'market': return 'danger'
    case 'limit': return 'primary'
    case 'stop': return 'warning'
    case 'stop_limit': return 'warning'
    case 'trailing_stop': return 'info'
    default: return 'info'
  }
}

const getOrderTypeText = (type: string) => {
  switch (type) {
    case 'market': return '市价单'
    case 'limit': return '限价单'
    case 'stop': return '止损单'
    case 'stop_limit': return '止损限价单'
    case 'trailing_stop': return '跟踪止损'
    default: return type
  }
}

const getOrderStatusTagType = (status: string) => {
  switch (status) {
    case 'pending': return 'info'
    case 'open': return 'primary'
    case 'filled': return 'success'
    case 'partially_filled': return 'warning'
    case 'cancelled': return 'danger'
    case 'rejected': return 'danger'
    case 'expired': return 'info'
    default: return 'info'
  }
}

const getOrderStatusText = (status: string) => {
  switch (status) {
    case 'pending': return '等待中'
    case 'open': return '已挂单'
    case 'filled': return '已成交'
    case 'partially_filled': return '部分成交'
    case 'cancelled': return '已取消'
    case 'rejected': return '已拒绝'
    case 'expired': return '已过期'
    default: return status
  }
}

const getOrderSourceText = (source: string) => {
  switch (source) {
    case 'manual': return '手动'
    case 'strategy': return '策略'
    case 'api': return 'API'
    case 'tp_sl': return '止盈止损'
    default: return source
  }
}

const getTimeInForceText = (tif: string) => {
  switch (tif) {
    case 'GTC': return 'GTC - 成交为止'
    case 'IOC': return 'IOC - 立即成交或取消'
    case 'FOK': return 'FOK - 全部成交或取消'
    default: return tif
  }
}

const canEditOrder = (order: any) => {
  // Only pending or open limit orders can be edited
  return ['pending', 'open'].includes(order.status) && order.type !== 'market'
}

const canCancelOrder = (order: any) => {
  // Orders can be cancelled if they are not already filled, cancelled, rejected, or expired
  return !['filled', 'cancelled', 'rejected', 'expired'].includes(order.status)
}

// Data loading functions
const refreshOrders = async () => {
  try {
    loading.value = true
    
    const { data } = await getActiveOrders({
      page: currentPage.value,
      limit: pageSize.value
    })
    
    activeOrders.value = data.orders || []
    totalActiveOrdersCount.value = data.total || 0
    
    ElMessage.success('订单数据已刷新')
  } catch (err) {
    console.error('加载订单数据失败:', err)
    ElMessage.error('加载订单数据失败')
  } finally {
    loading.value = false
  }
}

const loadOrderHistory = async () => {
  try {
    historyLoading.value = true
    
    const [startDate, endDate] = historyDateRange.value
    
    const { data } = await getOrderHistory({
      startDate,
      endDate,
      page: historyCurrentPage.value,
      limit: historyPageSize.value
    })
    
    orderHistory.value = data.orders || []
    totalHistoryCount.value = data.total || 0
  } catch (err) {
    console.error('加载订单历史失败:', err)
    ElMessage.error('加载订单历史失败')
  } finally {
    historyLoading.value = false
  }
}

const updateAnalytics = async () => {
  try {
    analyticsLoading.value = true
    
    const { data } = await getOrderAnalytics({
      timeRange: analyticsTimeRange.value
    })
    
    // Update analytics data
    Object.assign(analytics, data)
    
    // Initialize charts
    nextTick(() => {
      initOrderVolumeChart()
      initOrderTypeDistributionChart()
    })
  } catch (err) {
    console.error('加载分析数据失败:', err)
    ElMessage.error('加载分析数据失败')
  } finally {
    analyticsLoading.value = false
  }
}

const loadOrderDetail = async (orderId: string) => {
  try {
    const { data } = await getOrderDetail(orderId)
    currentOrder.value = data
    
    // Load order fill history
    const fillsResponse = await getOrderFills(orderId)
    orderFillHistory.value = fillsResponse.data || []
  } catch (err) {
    console.error('加载订单详情失败:', err)
    ElMessage.error('加载订单详情失败')
  }
}

const loadOrderBook = async (symbol: string = currentSymbol.value) => {
  try {
    const { data } = await getOrderBook(symbol)
    
    // Process order book data to calculate totals and percentages
    const maxTotal = Math.max(
      data.asks.reduce((max: number, ask: any) => Math.max(max, ask.amount * ask.price), 0),
      data.bids.reduce((max: number, bid: any) => Math.max(max, bid.amount * bid.price), 0)
    )
    
    // Process asks (sell orders)
    let askTotal = 0
    const processedAsks = data.asks.slice(0, 10).map((ask: any) => {
      askTotal += ask.amount
      const total = ask.amount * ask.price
      return {
        price: ask.price,
        amount: ask.amount,
        total,
        percentage: (total / maxTotal) * 100
      }
    })
    
    // Process bids (buy orders)
    let bidTotal = 0
    const processedBids = data.bids.slice(0, 10).map((bid: any) => {
      bidTotal += bid.amount
      const total = bid.amount * bid.price
      return {
        price: bid.price,
        amount: bid.amount,
        total,
        percentage: (total / maxTotal) * 100
      }
    })
    
    // Update order book data
    orderBookData.asks = processedAsks
    orderBookData.bids = processedBids
    orderBookData.timestamp = data.timestamp
  } catch (err) {
    console.error('加载订单簿数据失败:', err)
    ElMessage.error('加载订单簿数据失败')
  }
}

// Chart initialization
const initOrderVolumeChart = () => {
  if (!orderVolumeChartRef.value) return
  
  if (!orderVolumeChart) {
    orderVolumeChart = echarts.init(orderVolumeChartRef.value)
  }
  
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    legend: {
      data: ['买入订单', '卖出订单', '总成交量']
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: analytics.volumeTrend?.map((item: any) => item.date) || []
    },
    yAxis: [
      {
        type: 'value',
        name: '订单数',
        axisLabel: {
          formatter: '{value}'
        }
      },
      {
        type: 'value',
        name: '成交量',
        axisLabel: {
          formatter: '{value}'
        }
      }
    ],
    series: [
      {
        name: '买入订单',
        type: