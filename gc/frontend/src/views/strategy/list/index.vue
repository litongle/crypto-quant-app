<template>
  <div class="strategy-list-container">
    <!-- Page header with title and actions -->
    <div class="page-header">
      <div class="header-title">
        <el-icon><Connection /></el-icon>
        <h2>策略管理</h2>
      </div>
      <div class="header-actions">
        <el-button-group>
          <el-button
            type="primary"
            :icon="Plus"
            @click="navigateToCreate"
          >
            新建策略
          </el-button>
          <el-button
            type="success"
            :icon="CopyDocument"
            :disabled="!hasSelectedStrategies"
            @click="cloneSelectedStrategies"
          >
            克隆策略
          </el-button>
          <el-button
            type="danger"
            :icon="Delete"
            :disabled="!hasSelectedStrategies"
            @click="confirmBatchDelete"
          >
            批量删除
          </el-button>
          <el-dropdown trigger="click" @command="handleExport">
            <el-button :icon="Download">
              导出
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="exportSelected" :disabled="!hasSelectedStrategies">导出选中</el-dropdown-item>
                <el-dropdown-item command="exportAll">导出全部</el-dropdown-item>
                <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button
            type="primary"
            :icon="Upload"
            @click="showImportDialog"
          >
            导入
          </el-button>
        </el-button-group>
      </div>
    </div>

    <!-- Filters section -->
    <el-card class="filter-card" shadow="never">
      <div class="filter-container">
        <el-form :inline="true" :model="filterForm" @submit.prevent>
          <el-form-item label="策略名称">
            <el-input
              v-model="filterForm.name"
              placeholder="输入策略名称"
              clearable
              @input="handleFilterChange"
            />
          </el-form-item>
          
          <el-form-item label="策略类型">
            <el-select
              v-model="filterForm.type"
              placeholder="选择类型"
              clearable
              @change="handleFilterChange"
            >
              <el-option
                v-for="item in strategyTypeOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          
          <el-form-item label="状态">
            <el-select
              v-model="filterForm.status"
              placeholder="选择状态"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="运行中" value="running" />
              <el-option label="已暂停" value="paused" />
              <el-option label="已停止" value="stopped" />
              <el-option label="错误" value="error" />
            </el-select>
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
          
          <el-form-item label="绩效">
            <el-select
              v-model="filterForm.performance"
              placeholder="绩效筛选"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="盈利" value="profit" />
              <el-option label="亏损" value="loss" />
              <el-option label="高胜率 (>60%)" value="high_win_rate" />
              <el-option label="低胜率 (<40%)" value="low_win_rate" />
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
          
          <el-form-item label="胜率范围">
            <el-slider
              v-model="advancedFilterForm.winRateRange"
              range
              :min="0"
              :max="100"
              :marks="{0: '0%', 25: '25%', 50: '50%', 75: '75%', 100: '100%'}"
              @change="handleFilterChange"
            />
          </el-form-item>
          
          <el-form-item label="盈亏范围">
            <el-slider
              v-model="advancedFilterForm.pnlRange"
              range
              :min="-100"
              :max="100"
              :marks="{'-100': '-100%', '-50': '-50%', 0: '0%', 50: '50%', 100: '100%'}"
              @change="handleFilterChange"
            />
          </el-form-item>
          
          <el-form-item label="交易次数">
            <el-input-number
              v-model="advancedFilterForm.minTrades"
              placeholder="最小交易次数"
              :min="0"
              :step="10"
              @change="handleFilterChange"
            />
            <span class="range-separator">至</span>
            <el-input-number
              v-model="advancedFilterForm.maxTrades"
              placeholder="最大交易次数"
              :min="0"
              :step="10"
              @change="handleFilterChange"
            />
          </el-form-item>
          
          <el-form-item label="创建者">
            <el-select
              v-model="advancedFilterForm.creator"
              placeholder="选择创建者"
              clearable
              @change="handleFilterChange"
            >
              <el-option
                v-for="item in creatorOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          
          <el-form-item label="标签">
            <el-select
              v-model="advancedFilterForm.tags"
              placeholder="选择标签"
              multiple
              clearable
              collapse-tags
              @change="handleFilterChange"
            >
              <el-option
                v-for="item in tagOptions"
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
            <div class="statistic-title">策略总数</div>
            <div class="statistic-value">{{ totalStrategies }}</div>
            <div class="statistic-footer">
              <span>运行中: {{ runningStrategies }}</span>
              <span>已暂停: {{ pausedStrategies }}</span>
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
            <div class="statistic-title">平均胜率</div>
            <div class="statistic-value">{{ formatPercentage(avgWinRate) }}</div>
            <div class="statistic-footer">
              <el-progress
                :percentage="avgWinRate"
                :stroke-width="5"
                :show-text="false"
                :color="winRateColor"
              />
            </div>
          </el-card>
        </el-col>
        
        <el-col :xs="24" :sm="12" :md="6">
          <el-card shadow="hover" class="statistic-card">
            <div class="statistic-title">最佳策略</div>
            <div class="statistic-value">{{ bestStrategy?.name || '无数据' }}</div>
            <div class="statistic-footer">
              <span>收益率: {{ formatPercentage(bestStrategy?.returnRate || 0) }}</span>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- Strategy comparison -->
    <el-card v-if="showComparison" shadow="never" class="comparison-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>策略对比</span>
            <el-tag type="info" size="small">{{ selectedStrategies.length }}</el-tag>
          </div>
          <div class="header-right">
            <el-button type="danger" size="small" @click="closeComparison">关闭对比</el-button>
          </div>
        </div>
      </template>
      
      <div class="comparison-container">
        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>累计收益对比</h3>
              <div ref="comparisonReturnsChartRef" class="comparison-chart"></div>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div class="chart-container">
              <h3>胜率和交易次数对比</h3>
              <div ref="comparisonWinRateChartRef" class="comparison-chart"></div>
            </div>
          </el-col>
        </el-row>
        
        <div class="comparison-table-container">
          <h3>策略绩效对比</h3>
          <el-table
            :data="selectedStrategies"
            style="width: 100%"
            border
            stripe
            size="small"
          >
            <el-table-column prop="name" label="策略名称" width="150" />
            <el-table-column prop="type" label="类型" width="120">
              <template #default="scope">
                {{ getStrategyTypeLabel(scope.row.type) }}
              </template>
            </el-table-column>
            <el-table-column prop="totalTrades" label="交易次数" width="100" sortable />
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
            <el-table-column prop="returnRate" label="收益率" width="120" sortable>
              <template #default="scope">
                <span :class="{ 'profit': scope.row.returnRate > 0, 'loss': scope.row.returnRate < 0 }">
                  {{ formatPercentage(scope.row.returnRate) }}
                </span>
              </template>
            </el-table-column>
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

    <!-- Strategies table -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>策略列表</span>
            <el-tag type="info" size="small">{{ filteredStrategies.length }}</el-tag>
          </div>
          <div class="header-right">
            <el-input
              v-model="searchKeyword"
              placeholder="搜索策略..."
              prefix-icon="Search"
              clearable
              @input="handleSearch"
            />
            <el-tooltip content="表格设置" placement="top">
              <el-button :icon="Setting" circle @click="showTableSettings = true" />
            </el-tooltip>
            <el-button 
              type="primary" 
              plain 
              size="small" 
              :icon="Sort" 
              @click="toggleComparisonMode"
            >
              {{ showComparison ? '取消对比' : '对比所选' }}
            </el-button>
            <el-button 
              type="success" 
              plain 
              size="small" 
              :icon="RefreshRight" 
              :disabled="!hasSelectedStrategies"
              @click="batchStartStrategies"
            >
              批量启动
            </el-button>
            <el-button 
              type="warning" 
              plain 
              size="small" 
              :icon="VideoPause" 
              :disabled="!hasSelectedStrategies"
              @click="batchPauseStrategies"
            >
              批量暂停
            </el-button>
          </div>
        </div>
      </template>
      
      <!-- Table loading state -->
      <div v-if="loading" class="loading-container">
        <el-spin class="loading-spinner" />
        <span>加载策略数据...</span>
      </div>
      
      <!-- Empty state -->
      <el-empty
        v-else-if="filteredStrategies.length === 0"
        description="暂无策略数据"
      >
        <template #image>
          <el-icon class="empty-icon"><Connection /></el-icon>
        </template>
        <el-button type="primary" @click="navigateToCreate">创建策略</el-button>
      </el-empty>
      
      <!-- Strategies table -->
      <el-table
        v-else
        ref="strategiesTableRef"
        :data="paginatedStrategies"
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
            <div class="strategy-detail">
              <el-tabs v-model="activeTab">
                <el-tab-pane label="基本信息" name="info">
                  <el-descriptions :column="3" border>
                    <el-descriptions-item label="策略ID">{{ props.row.id }}</el-descriptions-item>
                    <el-descriptions-item label="创建时间">
                      {{ formatDateTime(props.row.createdAt) }}
                    </el-descriptions-item>
                    <el-descriptions-item label="更新时间">
                      {{ formatDateTime(props.row.updatedAt) }}
                    </el-descriptions-item>
                    <el-descriptions-item label="创建者">
                      {{ props.row.creator }}
                    </el-descriptions-item>
                    <el-descriptions-item label="标签">
                      <el-tag 
                        v-for="tag in props.row.tags" 
                        :key="tag" 
                        size="small" 
                        class="tag-item"
                      >
                        {{ tag }}
                      </el-tag>
                    </el-descriptions-item>
                    <el-descriptions-item label="描述">
                      {{ props.row.description || '无描述' }}
                    </el-descriptions-item>
                  </el-descriptions>
                </el-tab-pane>
                
                <el-tab-pane label="参数配置" name="params">
                  <el-descriptions :column="2" border>
                    <el-descriptions-item v-for="(value, key) in props.row.parameters" :key="key" :label="key">
                      {{ value }}
                    </el-descriptions-item>
                  </el-descriptions>
                </el-tab-pane>
                
                <el-tab-pane label="绩效指标" name="performance">
                  <el-row :gutter="20">
                    <el-col :xs="24" :md="12">
                      <div class="chart-container">
                        <h3>累计收益</h3>
                        <div :id="`returns-chart-${props.row.id}`" class="performance-chart"></div>
                      </div>
                    </el-col>
                    <el-col :xs="24" :md="12">
                      <div class="chart-container">
                        <h3>每日盈亏</h3>
                        <div :id="`daily-pnl-chart-${props.row.id}`" class="performance-chart"></div>
                      </div>
                    </el-col>
                  </el-row>
                  <el-row :gutter="20" class="metrics-row">
                    <el-col :xs="12" :sm="8" :md="6">
                      <div class="metric-card">
                        <div class="metric-title">总收益率</div>
                        <div class="metric-value" :class="{ 'profit': props.row.returnRate > 0, 'loss': props.row.returnRate < 0 }">
                          {{ formatPercentage(props.row.returnRate) }}
                        </div>
                      </div>
                    </el-col>
                    <el-col :xs="12" :sm="8" :md="6">
                      <div class="metric-card">
                        <div class="metric-title">胜率</div>
                        <div class="metric-value">{{ formatPercentage(props.row.winRate) }}</div>
                      </div>
                    </el-col>
                    <el-col :xs="12" :sm="8" :md="6">
                      <div class="metric-card">
                        <div class="metric-title">夏普比率</div>
                        <div class="metric-value">{{ props.row.sharpeRatio.toFixed(2) }}</div>
                      </div>
                    </el-col>
                    <el-col :xs="12" :sm="8" :md="6">
                      <div class="metric-card">
                        <div class="metric-title">最大回撤</div>
                        <div class="metric-value loss">{{ formatPercentage(props.row.maxDrawdown) }}</div>
                      </div>
                    </el-col>
                    <el-col :xs="12" :sm="8" :md="6">
                      <div class="metric-card">
                        <div class="metric-title">盈亏比</div>
                        <div class="metric-value">{{ props.row.profitLossRatio.toFixed(2) }}</div>
                      </div>
                    </el-col>
                    <el-col :xs="12" :sm="8" :md="6">
                      <div class="metric-card">
                        <div class="metric-title">交易次数</div>
                        <div class="metric-value">{{ props.row.totalTrades }}</div>
                      </div>
                    </el-col>
                  </el-row>
                </el-tab-pane>
                
                <el-tab-pane label="最近交易" name="trades">
                  <el-table
                    :data="props.row.recentTrades"
                    style="width: 100%"
                    border
                    stripe
                    size="small"
                  >
                    <el-table-column prop="time" label="时间" width="160">
                      <template #default="scope">
                        {{ formatDateTime(scope.row.time) }}
                      </template>
                    </el-table-column>
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
                    <el-table-column prop="pnl" label="盈亏" width="150">
                      <template #default="scope">
                        <span :class="{ 'profit': scope.row.pnl > 0, 'loss': scope.row.pnl < 0 }">
                          {{ formatCurrency(scope.row.pnl) }}
                          ({{ formatPercentage(scope.row.pnlPercentage) }})
                        </span>
                      </template>
                    </el-table-column>
                  </el-table>
                </el-tab-pane>
                
                <el-tab-pane label="日志记录" name="logs">
                  <div class="log-container">
                    <div v-for="(log, index) in props.row.logs" :key="index" class="log-entry">
                      <span class="log-time">{{ formatDateTime(log.time) }}</span>
                      <span :class="['log-level', `log-level-${log.level.toLowerCase()}`]">{{ log.level }}</span>
                      <span class="log-message">{{ log.message }}</span>
                    </div>
                  </div>
                </el-tab-pane>
              </el-tabs>
              
              <div class="strategy-actions">
                <el-button-group>
                  <el-button 
                    type="primary" 
                    :icon="Edit"
                    @click.stop="editStrategy(props.row)"
                  >
                    编辑
                  </el-button>
                  <el-button 
                    type="success" 
                    :icon="CopyDocument"
                    @click.stop="cloneStrategy(props.row)"
                  >
                    克隆
                  </el-button>
                  <el-button 
                    type="info" 
                    :icon="Histogram"
                    @click.stop="navigateToBacktest(props.row)"
                  >
                    回测
                  </el-button>
                  <el-button 
                    type="danger" 
                    :icon="Delete"
                    @click.stop="confirmDeleteStrategy(props.row)"
                  >
                    删除
                  </el-button>
                </el-button-group>
              </div>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="name" label="策略名称" min-width="150" sortable>
          <template #default="scope">
            <div class="strategy-name-cell">
              <el-tooltip v-if="scope.row.isTemplate" content="模板策略" placement="top">
                <el-icon class="template-icon"><Files /></el-icon>
              </el-tooltip>
              <span>{{ scope.row.name }}</span>
              <el-tag 
                v-if="scope.row.tags && scope.row.tags.length > 0" 
                size="small" 
                effect="plain"
              >
                {{ scope.row.tags[0] }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="type" label="类型" width="120">
          <template #default="scope">
            <el-tag effect="plain">
              {{ getStrategyTypeLabel(scope.row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="symbol" label="交易对" width="120">
          <template #default="scope">
            <div class="symbol-cell">
              <crypto-icon :symbol="getCryptoSymbol(scope.row.symbol)" class="crypto-icon" />
              <span>{{ scope.row.symbol }}</span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="getStatusTagType(scope.row.status)">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="totalTrades" label="交易次数" width="100" sortable>
          <template #default="scope">
            {{ scope.row.totalTrades }}
          </template>
        </el-table-column>
        
        <el-table-column prop="winRate" label="胜率" width="100" sortable>
          <template #default="scope">
            <div class="win-rate-cell">
              {{ formatPercentage(scope.row.winRate) }}
              <el-progress
                :percentage="scope.row.winRate"
                :stroke-width="4"
                :show-text="false"
                :color="getWinRateColor(scope.row.winRate)"
              />
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="totalPnl" label="总盈亏" width="150" sortable>
          <template #default="scope">
            <div 
              class="pnl-cell" 
              :class="{
                'profit': scope.row.totalPnl > 0,
                'loss': scope.row.totalPnl < 0
              }"
            >
              {{ formatCurrency(scope.row.totalPnl) }}
              <span class="pnl-percentage">
                ({{ formatPercentage(scope.row.returnRate) }})
              </span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="sharpeRatio" label="夏普比率" width="100" sortable>
          <template #default="scope">
            {{ scope.row.sharpeRatio.toFixed(2) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="maxDrawdown" label="最大回撤" width="100" sortable>
          <template #default="scope">
            <span class="loss">{{ formatPercentage(scope.row.maxDrawdown) }}</span>
          </template>
        </el-table-column>
        
        <el-table-column prop="enabled" label="启用" width="80">
          <template #default="scope">
            <el-switch
              v-model="scope.row.enabled"
              :loading="scope.row.switchLoading"
              @change="(val) => toggleStrategyStatus(scope.row, val)"
            />
          </template>
        </el-table-column>
        
        <el-table-column label="操作" fixed="right" width="150">
          <template #default="scope">
            <el-button-group>
              <el-tooltip content="编辑" placement="top">
                <el-button 
                  type="primary" 
                  :icon="Edit" 
                  circle
                  size="small"
                  @click.stop="editStrategy(scope.row)"
                />
              </el-tooltip>
              <el-tooltip content="回测" placement="top">
                <el-button 
                  type="info" 
                  :icon="Histogram" 
                  circle
                  size="small"
                  @click.stop="navigateToBacktest(scope.row)"
                />
              </el-tooltip>
              <el-tooltip content="删除" placement="top">
                <el-button 
                  type="danger" 
                  :icon="Delete" 
                  circle
                  size="small"
                  @click.stop="confirmDeleteStrategy(scope.row)"
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
          :total="filteredStrategies.length"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- Template Gallery -->
    <el-card shadow="never" class="template-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>策略模板库</span>
            <el-tag type="info" size="small">{{ strategyTemplates.length }}</el-tag>
          </div>
          <div class="header-right">
            <el-button type="primary" size="small" @click="navigateToTemplateManager">管理模板</el-button>
          </div>
        </div>
      </template>
      
      <div class="template-gallery">
        <el-row :gutter="20">
          <el-col :xs="24" :sm="12" :md="8" :lg="6" v-for="template in strategyTemplates" :key="template.id">
            <el-card shadow="hover" class="template-item">
              <template #header>
                <div class="template-header">
                  <span class="template-name">{{ template.name }}</span>
                  <el-tag size="small" effect="plain">{{ getStrategyTypeLabel(template.type) }}</el-tag>
                </div>
              </template>
              
              <div class="template-content">
                <p class="template-description">{{ template.description || '无描述' }}</p>
                
                <div class="template-stats">
                  <div class="stat-item">
                    <span class="stat-label">胜率</span>
                    <span class="stat-value">{{ formatPercentage(template.winRate) }}</span>
                  </div>
                  <div class="stat-item">
                    <span class="stat-label">收益率</span>
                    <span class="stat-value" :class="{ 'profit': template.returnRate > 0, 'loss': template.returnRate < 0 }">
                      {{ formatPercentage(template.returnRate) }}
                    </span>
                  </div>
                  <div class="stat-item">
                    <span class="stat-label">夏普比率</span>
                    <span class="stat-value">{{ template.sharpeRatio.toFixed(2) }}</span>
                  </div>
                </div>
                
                <div class="template-tags">
                  <el-tag 
                    v-for="tag in template.tags" 
                    :key="tag" 
                    size="small" 
                    class="tag-item"
                  >
                    {{ tag }}
                  </el-tag>
                </div>
                
                <div class="template-actions">
                  <el-button type="primary" size="small" @click="useTemplate(template)">使用模板</el-button>
                  <el-button type="info" size="small" @click="previewTemplate(template)">预览</el-button>
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </el-card>

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

    <!-- Import Dialog -->
    <el-dialog
      v-model="importDialogVisible"
      title="导入策略"
      width="500px"
    >
      <div class="import-dialog">
        <el-upload
          class="upload-container"
          drag
          action="#"
          :auto-upload="false"
          :on-change="handleFileChange"
          :limit="1"
        >
          <el-icon class="el-icon--upload"><Upload /></el-icon>
          <div class="el-upload__text">拖拽文件到此处或 <em>点击上传</em></div>
          <template #tip>
            <div class="el-upload__tip">
              支持 .json 格式的策略配置文件
            </div>
          </template>
        </el-upload>
        
        <div v-if="importFile" class="import-preview">
          <h3>文件预览</h3>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="文件名">{{ importFile.name }}</el-descriptions-item>
            <el-descriptions-item label="文件大小">{{ formatFileSize(importFile.size) }}</el-descriptions-item>
            <el-descriptions-item label="上传时间">{{ formatDateTime(new Date()) }}</el-descriptions-item>
          </el-descriptions>
          
          <div v-if="importPreview" class="preview-content">
            <h4>策略内容预览</h4>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="策略名称">{{ importPreview.name }}</el-descriptions-item>
              <el-descriptions-item label="策略类型">{{ getStrategyTypeLabel(importPreview.type) }}</el-descriptions-item>
              <el-descriptions-item label="交易对">{{ importPreview.symbol }}</el-descriptions-item>
              <el-descriptions-item label="描述">{{ importPreview.description || '无描述' }}</el-descriptions-item>
            </el-descriptions>
          </div>
        </div>
      </div>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="importDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="importLoading" :disabled="!importFile" @click="importStrategy">
            导入
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Template Preview Dialog -->
    <el-dialog
      v-model="templatePreviewVisible"
      title="模板预览"
      width="800px"
    >
      <div v-if="currentTemplate" class="template-preview">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="模板名称">{{ currentTemplate.name }}</el-descriptions-item>
          <el-descriptions-item label="策略类型">{{ getStrategyTypeLabel(currentTemplate.type) }}</el-descriptions-item>
          <el-descriptions-item label="交易对">{{ currentTemplate.symbol }}</el-descriptions-item>
          <el-descriptions-item label="创建者">{{ currentTemplate.creator }}</el-descriptions-item>
          <el-descriptions-item label="标签">
            <el-tag 
              v-for="tag in currentTemplate.tags" 
              :key="tag" 
              size="small" 
              class="tag-item"
            >
              {{ tag }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="描述">{{ currentTemplate.description || '无描述' }}</el-descriptions-item>
        </el-descriptions>
        
        <div class="template-parameters">
          <h3>参数配置</h3>
          <el-descriptions :column="2" border>
            <el-descriptions-item v-for="(value, key) in currentTemplate.parameters" :key="key" :label="key">
              {{ value }}
            </el-descriptions-item>
          </el-descriptions>
        </div>
        
        <div class="template-performance">
          <h3>绩效指标</h3>
          <el-row :gutter="20">
            <el-col :xs="24" :md="12">
              <div class="chart-container">
                <h4>累计收益</h4>
                <div ref="templateReturnsChartRef" class="template-chart"></div>
              </div>
            </el-col>
            <el-col :xs="24" :md="12">
              <div class="chart-container">
                <h4>每日盈亏</h4>
                <div ref="templatePnlChartRef" class="template-chart"></div>
              </div>
            </el-col>
          </el-row>
          <el-row :gutter="20" class="metrics-row">
            <el-col :xs="12" :sm="8" :md="6">
              <div class="metric-card">
                <div class="metric-title">总收益率</div>
                <div class="metric-value" :class="{ 'profit': currentTemplate.returnRate > 0, 'loss': currentTemplate.returnRate < 0 }">
                  {{ formatPercentage(currentTemplate.returnRate) }}
                </div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="8" :md="6">
              <div class="metric-card">
                <div class="metric-title">胜率</div>
                <div class="metric-value">{{ formatPercentage(currentTemplate.winRate) }}</div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="8" :md="6">
              <div class="metric-card">
                <div class="metric-title">夏普比率</div>
                <div class="metric-value">{{ currentTemplate.sharpeRatio.toFixed(2) }}</div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="8" :md="6">
              <div class="metric-card">
                <div class="metric-title">最大回撤</div>
                <div class="metric-value loss">{{ formatPercentage(currentTemplate.maxDrawdown) }}</div>
              </div>
            </el-col>
          </el-row>
        </div>
      </div>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="templatePreviewVisible = false">关闭</el-button>
          <el-button type="primary" @click="useTemplate(currentTemplate)">使用此模板</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Batch Delete Confirmation Dialog -->
    <el-dialog
      v-model="batchDeleteDialogVisible"
      title="批量删除策略"
      width="500px"
    >
      <div class="batch-delete-dialog">
        <p>您确定要删除以下 {{ selectedStrategies.length }} 个策略吗？此操作不可逆。</p>
        <el-table
          :data="selectedStrategies"
          style="width: 100%"
          size="small"
        >
          <el-table-column prop="name" label="策略名称" width="150" />
          <el-table-column prop="type" label="类型" width="120">
            <template #default="scope">
              {{ getStrategyTypeLabel(scope.row.type) }}
            </template>
          </el-table-column>
          <el-table-column prop="symbol" label="交易对" width="120" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="scope">
              <el-tag :type="getStatusTagType(scope.row.status)" size="small">
                {{ getStatusText(scope.row.status) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="batchDeleteDialogVisible = false">取消</el-button>
          <el-button type="danger" :loading="batchDeleteLoading" @click="executeBatchDelete">
            确认删除
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import { format, parseISO } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import { 
  Connection, 
  Plus, 
  CopyDocument, 
  Delete, 
  Download, 
  ArrowDown, 
  ArrowUp, 
  Search,
  Setting, 
  Edit, 
  Histogram, 
  Sort, 
  RefreshRight, 
  VideoPause, 
  Files,
  Upload
} from '@element-plus/icons-vue'
import { 
  getStrategies, 
  getStrategyTemplates,
  deleteStrategy,
  toggleStrategy,
  batchDeleteStrategies,
  batchStartStrategies as batchStart,
  batchPauseStrategies as batchPause,
  cloneStrategy as cloneStrategyApi,
  importStrategyConfig
} from '@/api/strategy'
import CryptoIcon from '@/components/CryptoIcon/index.vue'
import { exportToJson } from '@/utils/export'

const router = useRouter()

// State variables
const loading = ref(false)
const importLoading = ref(false)
const batchDeleteLoading = ref(false)
const advancedSearchVisible = ref(false)
const showTableSettings = ref(false)
const importDialogVisible = ref(false)
const templatePreviewVisible = ref(false)
const batchDeleteDialogVisible = ref(false)
const showComparison = ref(false)
const activeTab = ref('info')
const currentTemplate = ref<any>(null)
const selectedStrategies = ref<any[]>([])
const strategiesTableRef = ref<any>(null)
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const importFile = ref<File | null>(null)
const importPreview = ref<any>(null)

// Chart references
let comparisonReturnsChart: echarts.ECharts | null = null
let comparisonWinRateChart: echarts.ECharts | null = null
let templateReturnsChart: echarts.ECharts | null = null
let templatePnlChart: echarts.ECharts | null = null

const comparisonReturnsChartRef = ref<HTMLElement | null>(null)
const comparisonWinRateChartRef = ref<HTMLElement | null>(null)
const templateReturnsChartRef = ref<HTMLElement | null>(null)
const templatePnlChartRef = ref<HTMLElement | null>(null)

// Data
const strategies = ref<any[]>([])
const strategyTemplates = ref<any[]>([])

// Filter form
const filterForm = reactive({
  name: '',
  type: '',
  status: '',
  symbol: '',
  performance: ''
})

// Advanced filter form
const advancedFilterForm = reactive({
  dateRange: [] as string[],
  winRateRange: [0, 100],
  pnlRange: [-100, 100],
  minTrades: null as number | null,
  maxTrades: null as number | null,
  creator: '',
  tags: [] as string[]
})

// Options
const strategyTypeOptions = [
  { label: 'RSI分层策略', value: 'rsi_layered' },
  { label: 'MACD策略', value: 'macd' },
  { label: '布林带策略', value: 'bollinger' },
  { label: '双均线策略', value: 'dual_ma' },
  { label: '网格交易', value: 'grid' },
  { label: '自定义策略', value: 'custom' }
]

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

const creatorOptions = [
  { label: '系统', value: 'system' },
  { label: '管理员', value: 'admin' },
  { label: '用户1', value: 'user1' },
  { label: '用户2', value: 'user2' }
]

const tagOptions = [
  { label: '趋势跟踪', value: '趋势跟踪' },
  { label: '震荡策略', value: '震荡策略' },
  { label: '高频', value: '高频' },
  { label: '低频', value: '低频' },
  { label: '套利', value: '套利' },
  { label: '稳健', value: '稳健' },
  { label: '激进', value: '激进' }
]

// Table columns
const allColumns = [
  { prop: 'name', label: '策略名称', width: 150 },
  { prop: 'type', label: '类型', width: 120 },
  { prop: 'symbol', label: '交易对', width: 120 },
  { prop: 'status', label: '状态', width: 100 },
  { prop: 'totalTrades', label: '交易次数', width: 100 },
  { prop: 'winRate', label: '胜率', width: 100 },
  { prop: 'totalPnl', label: '总盈亏', width: 150 },
  { prop: 'sharpeRatio', label: '夏普比率', width: 100 },
  { prop: 'maxDrawdown', label: '最大回撤', width: 100 },
  { prop: 'enabled', label: '启用', width: 80 }
]

const visibleColumns = ref(allColumns.map(col => col.prop))

// Computed properties
const filteredStrategies = computed(() => {
  let result = [...strategies.value]
  
  // Apply filters
  if (filterForm.name) {
    result = result.filter(s => s.name.toLowerCase().includes(filterForm.name.toLowerCase()))
  }
  
  if (filterForm.type) {
    result = result.filter(s => s.type === filterForm.type)
  }
  
  if (filterForm.status) {
    result = result.filter(s => s.status === filterForm.status)
  }
  
  if (filterForm.symbol) {
    result = result.filter(s => s.symbol === filterForm.symbol)
  }
  
  if (filterForm.performance) {
    switch (filterForm.performance) {
      case 'profit':
        result = result.filter(s => s.totalPnl > 0)
        break
      case 'loss':
        result = result.filter(s => s.totalPnl < 0)
        break
      case 'high_win_rate':
        result = result.filter(s => s.winRate >= 60)
        break
      case 'low_win_rate':
        result = result.filter(s => s.winRate < 40)
        break
    }
  }
  
  // Apply advanced filters
  if (advancedFilterForm.dateRange && advancedFilterForm.dateRange.length === 2) {
    const [startDate, endDate] = advancedFilterForm.dateRange
    const start = new Date(startDate)
    const end = new Date(endDate)
    end.setHours(23, 59, 59, 999) // End of the day
    
    result = result.filter(s => {
      const created = new Date(s.createdAt)
      return created >= start && created <= end
    })
  }
  
  if (advancedFilterForm.winRateRange && advancedFilterForm.winRateRange.length === 2) {
    const [min, max] = advancedFilterForm.winRateRange
    result = result.filter(s => s.winRate >= min && s.winRate <= max)
  }
  
  if (advancedFilterForm.pnlRange && advancedFilterForm.pnlRange.length === 2) {
    const [min, max] = advancedFilterForm.pnlRange
    result = result.filter(s => {
      const returnRate = s.returnRate
      return returnRate >= min && returnRate <= max
    })
  }
  
  if (advancedFilterForm.minTrades !== null) {
    result = result.filter(s => s.totalTrades >= advancedFilterForm.minTrades!)
  }
  
  if (advancedFilterForm.maxTrades !== null) {
    result = result.filter(s => s.totalTrades <= advancedFilterForm.maxTrades!)
  }
  
  if (advancedFilterForm.creator) {
    result = result.filter(s => s.creator === advancedFilterForm.creator)
  }
  
  if (advancedFilterForm.tags && advancedFilterForm.tags.length > 0) {
    result = result.filter(s => {
      if (!s.tags) return false
      return advancedFilterForm.tags.some(tag => s.tags.includes(tag))
    })
  }
  
  // Apply search keyword
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(s => 
      s.name.toLowerCase().includes(keyword) ||
      s.description?.toLowerCase().includes(keyword) ||
      s.symbol.toLowerCase().includes(keyword)
    )
  }
  
  return result
})

const paginatedStrategies = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredStrategies.value.slice(start, end)
})

const totalStrategies = computed(() => strategies.value.length)
const runningStrategies = computed(() => strategies.value.filter(s => s.status === 'running').length)
const pausedStrategies = computed(() => strategies.value.filter(s => s.status === 'paused').length)
const totalPnl = computed(() => {
  return strategies.value.reduce((sum, s) => sum + s.totalPnl, 0)
})
const totalPnlPercentage = computed(() => {
  const totalInvestment = strategies.value.reduce((sum, s) => sum + s.initialCapital, 0)
  if (totalInvestment === 0) return 0
  return (totalPnl.value / totalInvestment) * 100
})
const avgWinRate = computed(() => {
  if (strategies.value.length === 0) return 0
  return strategies.value.reduce((sum, s) => sum + s.winRate, 0) / strategies.value.length
})
const winRateColor = computed(() => {
  if (avgWinRate.value < 40) return '#f56c6c'
  if (avgWinRate.value < 50) return '#e6a23c'
  return '#67c23a'
})
const bestStrategy = computed(() => {
  if (strategies.value.length === 0) return null
  
  return strategies.value.reduce((best, current) => {
    if (!best) return current
    return current.returnRate > best.returnRate ? current : best
  }, null)
})
const hasSelectedStrategies = computed(() => selectedStrategies.value.length > 0)

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

const formatDateTime = (dateStr: string | Date) => {
  if (!dateStr) return ''
  try {
    const date = typeof dateStr === 'string' ? parseISO(dateStr) : dateStr
    return format(date, 'yyyy-MM-dd HH:mm:ss', { locale: zhCN })
  } catch (e) {
    return String(dateStr)
  }
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const getCryptoSymbol = (symbol: string) => {
  return symbol.split('-')[0].toLowerCase()
}

const getStrategyTypeLabel = (type: string) => {
  const option = strategyTypeOptions.find(opt => opt.value === type)
  return option ? option.label : type
}

const getStatusTagType = (status: string) => {
  switch (status) {
    case 'running': return 'success'
    case 'paused': return 'warning'
    case 'stopped': return 'info'
    case 'error': return 'danger'
    default: return 'info'
  }
}

const getStatusText = (status: string) => {
  switch (status) {
    case 'running': return '运行中'
    case 'paused': return '已暂停'
    case 'stopped': return '已停止'
    case 'error': return '错误'
    default: return status
  }
}

const getWinRateColor = (winRate: number) => {
  if (winRate < 40) return '#f56c6c'
  if (winRate < 50) return '#e6a23c'
  return '#67c23a'
}

// Data loading functions
const loadStrategies = async () => {
  try {
    loading.value = true
    
    const { data } = await getStrategies()
    strategies.value = data.strategies || []
    
    // Initialize strategy charts after data is loaded
    nextTick(() => {
      strategies.value.forEach(strategy => {
        initStrategyCharts(strategy)
      })
    })
  } catch (err) {
    console.error('加载策略数据失败:', err)
    ElMessage.error('加载策略数据失败')
  } finally {
    loading.value = false
  }
}

const loadTemplates = async () => {
  try {
    const { data } = await getStrategyTemplates()
    strategyTemplates.value = data.templates || []
  } catch (err) {
    console.error('加载策略模板失败:', err)
    ElMessage.error('加载策略模板失败')
  }
}

// Chart initialization functions
const initStrategyCharts = (strategy: any) => {
  if (!strategy.returnsHistory || !strategy.dailyPnl) return
  
  nextTick(() => {
    // Returns chart
    const returnsChartElement = document.getElementById(`returns-chart-${strategy.id}`)
    if (returnsChartElement) {
      const returnsChart = echarts.init(returnsChartElement)
      
      const returnsOption = {
        tooltip: {
          trigger: 'axis',
          formatter: function(params: any) {
            const date = params[0].axisValue
            const value = params[0].data
            return `${date}<br/>累计收益: ${formatPercentage(value)}`
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
          data: strategy.returnsHistory.map((item: any) => item.date)
        },
        yAxis: {
          type: 'value',
          scale: true,
          axisLabel: {
            formatter: (value: number) => formatPercentage(value)
          }
        },
        series: [
          {
            name: '累计收益',
            type: 'line',
            data: strategy.returnsHistory.map((item: any) => item.value),
            areaStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: 'rgba(103, 194, 58, 0.5)' },
                { offset: 1, color: 'rgba(103, 194, 58, 0.1)' }
              ])
            },
            lineStyle: {
              width: 2,
              color: '#67C23A'
            }
          }
        ]
      }
      
      returnsChart.setOption(returnsOption)
    }
    
    // Daily PnL chart
    const dailyPnlChartElement = document.getElementById(`daily-pnl-chart-${strategy.id}`)
    if (dailyPnlChartElement) {
      const dailyPnlChart = echarts.init(dailyPnlChartElement)
      
      const dailyPnlOption = {
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
          data: strategy.dailyPnl.map((item: any) => item.date)
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
            data: strategy.dailyPnl.map((item: any) => item.value),
            itemStyle: {
              color: function(params: any) {
                return params.value >= 0 ? '#67C23A' : '#F56C6C'
              }
            }
          }
        ]
      }
      
      dailyPnlChart.setOption(dailyPnlOption)
    }
  })
}

const initComparisonCharts = () => {
  if (!comparisonReturnsChartRef.value || !comparisonWinRateChartRef.value || selectedStrategies.value.length === 0) return
  
  // Returns comparison chart
  if (!comparisonReturnsChart) {
    comparisonReturnsChart = echarts.init(comparisonReturnsChartRef.value)
  }
  
  const returnsData: any = {}
  const dates: string[] = []
  
  // Collect all dates from all strategies
  selectedStrategies.value.forEach(strategy => {
    if (strategy.returnsHistory) {
      strategy.returnsHistory.forEach((item: any) => {
        if (!dates.includes(item.date)) {
          dates.push(item.date)
        }
      })
    }
  })
  
  // Sort dates
  dates.sort()
  
  // Prepare series data
  const series = selectedStrategies.value.map(strategy => {
    const data = dates.map(date => {
      const found = strategy.returnsHistory?.find((item: any) => item.date === date)
      return found ? found.value : null
    })
    
    return {
      name: strategy.name,
      type: 'line',
      data,
      connectNulls: true
    }
  })
  
  const returnsOption = {
    tooltip: {
      trigger: 'axis'
    },
    legend: {
      data: selectedStrategies.value.map(s => s.name)
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: {
        formatter: (value: number) => formatPercentage(value)
      }
    },
    series
  }
  
  comparisonReturnsChart.setOption(returnsOption)
  
  // Win rate and trades comparison chart
  if (!comparisonWinRateChart) {
    comparisonWinRateChart = echarts.init(comparisonWinRateChartRef.value)
  }
  
  const winRateOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    legend: {
      data: ['胜率', '交易次数']
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: selectedStrategies.value.map(s => s.name)
    },
    yAxis: [
      {
        type: 'value',
        name: '胜率',
        min: 0,
        max: 100,
        axisLabel: {
          formatter: '{value}%'
        }
      },
      {
        type: 'value',
        name: '交易次数',
        axisLabel: {
          formatter: '{value}'
        }
      }
    ],
    series: [
      {
        name: '胜率',
        type: 'bar',
        data: selectedStrategies.value.map(s => s.winRate),
        itemStyle: {
          color: function(params: any) {
            const winRate = params.value
            return getWinRateColor(winRate)
          }
        }
      },
      {
        name: '交易次数',
        type: 'line',
        yAxisIndex: 1,
        data: selectedStrategies.value.map(s => s.totalTrades),
        symbol: 'circle',
        symbolSize: 8
      }
    ]
  }
  
  comparisonWinRateChart.setOption(winRateOption)
}

const initTemplateCharts = (template: any) => {
  if (!templateReturnsChartRef.value || !templatePnlChartRef.value || !template.returnsHistory || !template.dailyPnl) return
  
  // Template returns chart
  if (!templateReturnsChart) {
    templateReturnsChart = echarts.init(templateReturnsChartRef.value)
  }
  
  const returnsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: function(params: any) {
        const date = params[0].axisValue
        const value = params[0].data
        return `${date}<br/>累计收益: ${formatPercentage(value)}`
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
      data: template.returnsHistory.map((item: any) => item.date)
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: {
        formatter: (value: number) => formatPercentage(value)
      }
    },
    series: [
      {
        name: '累计收益',
        type: 'line',
        data: template.returnsHistory.map((item: any) => item.value),
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(103, 194, 58, 0.5)' },
            { offset: 1, color: 'rgba(103, 194, 58, 0.1)' }
          ])
        },
        lineStyle: {
          width: 2,
          color: '#67C23A'
        }
      }
    ]
  }
  
  templateReturnsChart.setOption(returnsOption)
  
  // Template daily PnL chart
  if (!templatePnlChart) {
    templatePnlChart = echarts.init(templatePnlChartRef.value)
  }
  
  const dailyPnlOption = {
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
      data: template.dailyPnl.map((item: any) => item.date)
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
        data: template.dailyPnl.map((item: any) => item.value),
        itemStyle: {
          color: function(params: any) {
            return params.value >= 0 ? '#67C23A' : '#F56C6C'
          }
        }
      }
    ]
  }
  
  templatePnlChart.setOption(dailyPnlOption)
}

// Event handlers
const handleFilterChange = () => {
  currentPage.value = 1
}

const resetFilters = () => {
  Object.keys(filterForm).forEach(key => {
    // @ts-ignore
    filterForm[key] = ''
  })
  
  Object.keys(advancedFilterForm).forEach(key => {
    if (key === 'winRateRange') {
      advancedFilterForm.winRateRange = [0, 100]
    } else if (key === 'pnlRange') {
      advancedFilterForm.pnlRange = [-100, 100]
    } else if (key === 'tags') {
      advancedFilterForm.tags = []
    } else if (key === 'dateRange') {
      advancedFilterForm.dateRange = []
    } else {
      // @ts-ignore
      advancedFilterForm[key] = null
    }
  })
  
  searchKeyword.value = ''
  currentPage.value = 1
}

const handleSearch = () => {
  currentPage.value = 1
}

const handleSizeChange = (val: number) => {
  pageSize.value = val
}

const handleCurrentChange = (val: number) => {
  currentPage.value = val
}

const handleSortChange = (column: any) => {
  if (!column.prop || !column.order) return
  
  const isAsc = column.order === 'ascending'
  
  strategies.value.sort((a, b) => {
    if (a[column.prop] === b[column.prop]) return 0
    
    if (isAsc) {
      return a[column.prop] < b[column.prop] ? -1 : 1
    } else {
      return a[column.prop] > b[column.prop] ? -1 : 1
    }
  })
}

const handleSelectionChange = (val: any[]) => {
  selectedStrategies.value = val
  
  if (showComparison.value && val.length >= 2) {
    nextTick(() => {
      initComparisonCharts()
    })
  }
}

const handleRowClick = (row: any) => {
  // Toggle selection when clicking on a row
  strategiesTableRef.value?.toggleRowSelection(row)
}

const toggleAdvancedSearch = () => {
  advancedSearchVisible.value = !advancedSearchVisible.value
}

const saveTableSettings = () => {
  // Save settings to local storage
  localStorage.setItem('strategyTableColumns', JSON.stringify(visibleColumns.value))
  localStorage.setItem('strategyTablePageSize', pageSize.value.toString())
  
  showTableSettings.value = false