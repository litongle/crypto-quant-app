import axios, { AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

// Base API configuration
const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'
const api = axios.create({
  baseURL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor for API calls
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor for API calls
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    const { response } = error
    
    if (response && response.status) {
      switch (response.status) {
        case 401:
          // Handle unauthorized error
          ElMessage.error('未授权，请重新登录')
          // Redirect to login page
          window.location.href = '/login'
          break
        case 403:
          ElMessage.error('没有权限访问该资源')
          break
        case 404:
          ElMessage.error('请求的资源不存在')
          break
        case 500:
          ElMessage.error('服务器错误，请稍后再试')
          break
        default:
          ElMessage.error(response.data?.message || '请求失败')
      }
    } else {
      // Network error
      ElMessage.error('网络错误，请检查您的网络连接')
    }
    
    return Promise.reject(error)
  }
)

// ===== TypeScript Interfaces =====

// Dashboard Data
export interface DashboardData {
  totalPnl: number
  totalPnlPercentage: number
  todayTrades: number
  successRate: number
  strategyStatus: 'running' | 'paused' | 'stopped'
  totalPositionValue: number
}

// Chart Data
export interface KlineData {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface ChartData {
  klines: [string, number, number, number, number, number][] // [timestamp, open, high, low, close, volume]
  currentPrice: number
  priceChange: number
  priceChangePercentage: number
  rsiValue: number
  volume: number
  signalDirection: 'buy' | 'sell' | ''
}

// Account Data
export interface AccountBalance {
  id: number
  name: string
  exchange: string
  balance: number
  available: number
  frozen: number
  updatedAt: string
}

// Trade Data
export interface Trade {
  id: number
  time: string
  symbol: string
  type: 'buy' | 'sell'
  price: number
  amount: number
  value: number
  fee: number
  pnl: number
  status: 'pending' | 'completed' | 'failed'
  strategyId: number
  strategyName: string
}

// Position Data
export interface Position {
  id: number
  symbol: string
  direction: 'long' | 'short'
  entryPrice: number
  currentPrice: number
  amount: number
  leverage: number
  margin: number
  unrealizedPnl: number
  unrealizedPnlPercentage: number
  liquidationPrice: number
  stopLoss: number | null
  takeProfit: number | null
  createdAt: string
  updatedAt: string
}

export interface PositionUpdateParams {
  stopLoss?: number | null
  takeProfit?: number | null
}

// Strategy Data
export interface StrategyPerformance {
  trades: number
  winRate: number
  profitFactor: number
  maxDrawdown: number
  equityCurve: {
    date: string
    equity: number
    benchmark: number
  }[]
}

// Market Data
export interface MarketTicker {
  symbol: string
  price: number
  change: number
  volume: number
  high24h: number
  low24h: number
}

// System Status
export interface SystemStatus {
  api: boolean
  database: boolean
  redis: boolean
  websocket: boolean
  exchange: boolean
  tasks: boolean
  resources: {
    cpu: number
    memory: number
    disk: number
  }
}

// ===== API Functions =====

// Dashboard Data
/**
 * Get dashboard overview data
 * @param timeRange Time range for the data ('today', '7d', '30d', 'all')
 * @returns Dashboard data
 */
export const getDashboardData = async (timeRange: string = 'today'): Promise<AxiosResponse<DashboardData>> => {
  try {
    return await api.get(`/v1/dashboard/overview`, {
      params: { timeRange }
    })
  } catch (error) {
    console.error('Failed to fetch dashboard data:', error)
    throw error
  }
}

// Chart Data
/**
 * Get chart data for a specific symbol and timeframe
 * @param symbol Trading symbol (e.g., 'ETH-USDT')
 * @param timeframe Timeframe (e.g., '1m', '5m', '15m', '1h', '4h', '1d')
 * @param limit Number of candles to retrieve
 * @returns Chart data
 */
export const getChartData = async (
  symbol: string,
  timeframe: string,
  limit: number = 100
): Promise<AxiosResponse<ChartData>> => {
  try {
    return await api.get(`/v1/market/klines`, {
      params: { symbol, timeframe, limit }
    })
  } catch (error) {
    console.error('Failed to fetch chart data:', error)
    throw error
  }
}

// Account Data
/**
 * Get account balances
 * @returns List of account balances
 */
export const getAccountBalances = async (): Promise<AxiosResponse<AccountBalance[]>> => {
  try {
    return await api.get('/v1/accounts/balances')
  } catch (error) {
    console.error('Failed to fetch account balances:', error)
    throw error
  }
}

/**
 * Sync account balances with exchange
 * @param accountId Optional account ID to sync specific account
 * @returns Success status
 */
export const syncAccountBalances = async (accountId?: number): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post('/v1/accounts/sync', { accountId })
  } catch (error) {
    console.error('Failed to sync account balances:', error)
    throw error
  }
}

// Trade Data
/**
 * Get recent trades
 * @param limit Number of trades to retrieve
 * @param offset Offset for pagination
 * @returns List of recent trades
 */
export const getRecentTrades = async (
  limit: number = 20,
  offset: number = 0
): Promise<AxiosResponse<Trade[]>> => {
  try {
    return await api.get('/v1/trades/recent', {
      params: { limit, offset }
    })
  } catch (error) {
    console.error('Failed to fetch recent trades:', error)
    throw error
  }
}

/**
 * Get trade history
 * @param startDate Start date for filtering
 * @param endDate End date for filtering
 * @param symbol Optional symbol filter
 * @param strategyId Optional strategy ID filter
 * @param limit Number of trades to retrieve
 * @param offset Offset for pagination
 * @returns List of trade history
 */
export const getTradeHistory = async (
  startDate: string,
  endDate: string,
  symbol?: string,
  strategyId?: number,
  limit: number = 50,
  offset: number = 0
): Promise<AxiosResponse<Trade[]>> => {
  try {
    return await api.get('/v1/trades/history', {
      params: {
        startDate,
        endDate,
        symbol,
        strategyId,
        limit,
        offset
      }
    })
  } catch (error) {
    console.error('Failed to fetch trade history:', error)
    throw error
  }
}

// Position Data
/**
 * Get active positions
 * @returns List of active positions
 */
export const getActivePositions = async (): Promise<AxiosResponse<Position[]>> => {
  try {
    return await api.get('/v1/positions/active')
  } catch (error) {
    console.error('Failed to fetch active positions:', error)
    throw error
  }
}

/**
 * Update position
 * @param positionId Position ID
 * @param params Parameters to update
 * @returns Updated position
 */
export const updatePosition = async (
  positionId: number,
  params: PositionUpdateParams
): Promise<AxiosResponse<Position>> => {
  try {
    return await api.patch(`/v1/positions/${positionId}`, params)
  } catch (error) {
    console.error('Failed to update position:', error)
    throw error
  }
}

/**
 * Close position
 * @param positionId Position ID
 * @returns Success status
 */
export const closePosition = async (positionId: number): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post(`/v1/positions/${positionId}/close`)
  } catch (error) {
    console.error('Failed to close position:', error)
    throw error
  }
}

/**
 * Get position history
 * @param startDate Start date for filtering
 * @param endDate End date for filtering
 * @param symbol Optional symbol filter
 * @param limit Number of positions to retrieve
 * @param offset Offset for pagination
 * @returns List of position history
 */
export const getPositionHistory = async (
  startDate: string,
  endDate: string,
  symbol?: string,
  limit: number = 50,
  offset: number = 0
): Promise<AxiosResponse<Position[]>> => {
  try {
    return await api.get('/v1/positions/history', {
      params: {
        startDate,
        endDate,
        symbol,
        limit,
        offset
      }
    })
  } catch (error) {
    console.error('Failed to fetch position history:', error)
    throw error
  }
}

// Strategy Data
/**
 * Get strategy performance
 * @param strategyId Strategy ID or name
 * @param timeRange Time range for the data ('today', '7d', '30d', 'all')
 * @returns Strategy performance data
 */
export const getStrategyPerformance = async (
  strategyId: string | number,
  timeRange: string = '30d'
): Promise<AxiosResponse<StrategyPerformance>> => {
  try {
    return await api.get(`/v1/strategies/${strategyId}/performance`, {
      params: { timeRange }
    })
  } catch (error) {
    console.error('Failed to fetch strategy performance:', error)
    throw error
  }
}

/**
 * Get all strategies
 * @returns List of strategies
 */
export const getStrategies = async (): Promise<AxiosResponse<any[]>> => {
  try {
    return await api.get('/v1/strategies')
  } catch (error) {
    console.error('Failed to fetch strategies:', error)
    throw error
  }
}

/**
 * Start strategy
 * @param strategyId Strategy ID or name
 * @returns Success status
 */
export const startStrategy = async (strategyId: string | number): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post(`/v1/strategies/${strategyId}/start`)
  } catch (error) {
    console.error('Failed to start strategy:', error)
    throw error
  }
}

/**
 * Pause strategy
 * @param strategyId Strategy ID or name
 * @returns Success status
 */
export const pauseStrategy = async (strategyId: string | number): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post(`/v1/strategies/${strategyId}/pause`)
  } catch (error) {
    console.error('Failed to pause strategy:', error)
    throw error
  }
}

/**
 * Stop strategy
 * @param strategyId Strategy ID or name
 * @returns Success status
 */
export const stopStrategy = async (strategyId: string | number): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post(`/v1/strategies/${strategyId}/stop`)
  } catch (error) {
    console.error('Failed to stop strategy:', error)
    throw error
  }
}

/**
 * Update strategy parameters
 * @param strategyId Strategy ID or name
 * @param params Strategy parameters
 * @returns Updated strategy
 */
export const updateStrategyParams = async (
  strategyId: string | number,
  params: Record<string, any>
): Promise<AxiosResponse<any>> => {
  try {
    return await api.patch(`/v1/strategies/${strategyId}/params`, params)
  } catch (error) {
    console.error('Failed to update strategy parameters:', error)
    throw error
  }
}

// Market Data
/**
 * Get market overview
 * @returns Market overview data
 */
export const getMarketOverview = async (): Promise<AxiosResponse<MarketTicker[]>> => {
  try {
    return await api.get('/v1/market/overview')
  } catch (error) {
    console.error('Failed to fetch market overview:', error)
    throw error
  }
}

/**
 * Get ticker data for a specific symbol
 * @param symbol Trading symbol (e.g., 'ETH-USDT')
 * @returns Ticker data
 */
export const getTickerData = async (symbol: string): Promise<AxiosResponse<MarketTicker>> => {
  try {
    return await api.get(`/v1/market/ticker/${symbol}`)
  } catch (error) {
    console.error('Failed to fetch ticker data:', error)
    throw error
  }
}

/**
 * Get order book for a specific symbol
 * @param symbol Trading symbol (e.g., 'ETH-USDT')
 * @param depth Order book depth
 * @returns Order book data
 */
export const getOrderBook = async (symbol: string, depth: number = 20): Promise<AxiosResponse<any>> => {
  try {
    return await api.get(`/v1/market/orderbook/${symbol}`, {
      params: { depth }
    })
  } catch (error) {
    console.error('Failed to fetch order book:', error)
    throw error
  }
}

// System Status
/**
 * Get system status
 * @returns System status data
 */
export const getSystemStatus = async (): Promise<AxiosResponse<SystemStatus>> => {
  try {
    return await api.get('/v1/system/status')
  } catch (error) {
    console.error('Failed to fetch system status:', error)
    throw error
  }
}

/**
 * Restart system service
 * @param service Service name (e.g., 'api', 'worker', 'all')
 * @returns Success status
 */
export const restartService = async (service: string): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post('/v1/system/restart', { service })
  } catch (error) {
    console.error('Failed to restart service:', error)
    throw error
  }
}

// Trading Control Actions
/**
 * Emergency stop trading
 * @returns Success status
 */
export const emergencyStopTrading = async (): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post('/v1/trading/emergency-stop')
  } catch (error) {
    console.error('Failed to execute emergency stop:', error)
    throw error
  }
}

/**
 * Place manual order
 * @param params Order parameters
 * @returns Order result
 */
export const placeManualOrder = async (params: {
  symbol: string
  type: 'market' | 'limit'
  side: 'buy' | 'sell'
  amount: number
  price?: number
  leverage?: number
  stopLoss?: number
  takeProfit?: number
}): Promise<AxiosResponse<any>> => {
  try {
    return await api.post('/v1/trading/orders', params)
  } catch (error) {
    console.error('Failed to place order:', error)
    throw error
  }
}

/**
 * Cancel order
 * @param orderId Order ID
 * @returns Success status
 */
export const cancelOrder = async (orderId: string): Promise<AxiosResponse<{ success: boolean }>> => {
  try {
    return await api.post(`/v1/trading/orders/${orderId}/cancel`)
  } catch (error) {
    console.error('Failed to cancel order:', error)
    throw error
  }
}

/**
 * Get open orders
 * @param symbol Optional symbol filter
 * @returns List of open orders
 */
export const getOpenOrders = async (symbol?: string): Promise<AxiosResponse<any[]>> => {
  try {
    return await api.get('/v1/trading/orders/open', {
      params: { symbol }
    })
  } catch (error) {
    console.error('Failed to fetch open orders:', error)
    throw error
  }
}

/**
 * Get WebSocket authentication token
 * @returns WebSocket authentication token
 */
export const getWebSocketToken = async (): Promise<AxiosResponse<{ token: string }>> => {
  try {
    return await api.get('/v1/ws/token')
  } catch (error) {
    console.error('Failed to fetch WebSocket token:', error)
    throw error
  }
}

export default api
