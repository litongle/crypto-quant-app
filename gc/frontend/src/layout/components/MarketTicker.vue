<template>
  <div class="market-ticker-container" v-show="!isMobile">
    <div class="ticker-wrapper">
      <div class="ticker-status" :class="{ 'connected': isConnected, 'error': hasError }">
        <el-icon v-if="isConnected"><Connection /></el-icon>
        <el-icon v-else><WarningFilled /></el-icon>
      </div>
      
      <div class="ticker-content" ref="tickerContent">
        <transition-group name="ticker-slide" tag="div" class="ticker-items">
          <div 
            v-for="(ticker, index) in visibleTickers" 
            :key="ticker.symbol" 
            class="ticker-item"
            :class="{ 'active': activeIndex === index }"
          >
            <div class="ticker-symbol">{{ formatSymbol(ticker.symbol) }}</div>
            <div class="ticker-price" :class="getPriceChangeClass(ticker)">
              {{ formatPrice(ticker.price) }}
            </div>
            <div class="ticker-change" :class="getChangeClass(ticker)">
              {{ formatChange(ticker.change_percentage) }}
            </div>
            <div class="ticker-volume">
              成交: {{ formatVolume(ticker.volume_24h) }}
            </div>
          </div>
        </transition-group>
      </div>
      
      <div class="ticker-controls">
        <el-button 
          type="text" 
          size="small" 
          @click="prevTicker" 
          :disabled="!canNavigate"
        >
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <div class="ticker-dots">
          <span 
            v-for="(_, index) in tickers" 
            :key="index" 
            class="ticker-dot" 
            :class="{ 'active': activeIndex === index }"
            @click="setActiveTicker(index)"
          ></span>
        </div>
        <el-button 
          type="text" 
          size="small" 
          @click="nextTicker" 
          :disabled="!canNavigate"
        >
          <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
    </div>
    
    <!-- Error tooltip -->
    <el-tooltip
      v-if="hasError"
      effect="dark"
      :content="errorMessage"
      placement="bottom"
      :visible="showErrorTooltip"
    >
      <div class="error-icon" @mouseenter="showErrorTooltip = true" @mouseleave="showErrorTooltip = false">
        <el-icon><WarningFilled /></el-icon>
      </div>
    </el-tooltip>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useAppStore } from '@/store/modules/app'
import { storeToRefs } from 'pinia'
import { 
  Connection, WarningFilled, ArrowLeft, ArrowRight
} from '@element-plus/icons-vue'
import { useWebSocket } from '@/composables/useWebSocket'

// App store for responsive design
const appStore = useAppStore()
const { device } = storeToRefs(appStore)

// Computed property to check if on mobile
const isMobile = computed(() => device.value === 'mobile')

// WebSocket connection
const { 
  connect, 
  disconnect, 
  connected: isConnected, 
  lastMessage, 
  error: wsError 
} = useWebSocket()

// Ticker data
interface TickerData {
  symbol: string
  price: number
  previous_price?: number
  change_percentage: number
  volume_24h: number
  last_updated: Date
  flash_direction?: 'up' | 'down' | null
  flash_timeout?: NodeJS.Timeout
}

// State variables
const tickers = ref<TickerData[]>([
  {
    symbol: 'ETH-USDT',
    price: 0,
    change_percentage: 0,
    volume_24h: 0,
    last_updated: new Date()
  },
  {
    symbol: 'BTC-USDT',
    price: 0,
    change_percentage: 0,
    volume_24h: 0,
    last_updated: new Date()
  },
  {
    symbol: 'SOL-USDT',
    price: 0,
    change_percentage: 0,
    volume_24h: 0,
    last_updated: new Date()
  }
])

const activeIndex = ref(0)
const autoScrollInterval = ref<NodeJS.Timeout | null>(null)
const hasError = ref(false)
const errorMessage = ref('')
const showErrorTooltip = ref(false)
const tickerContent = ref<HTMLElement | null>(null)
const isAutoScrolling = ref(true)

// Computed properties
const visibleTickers = computed(() => {
  return tickers.value
})

const canNavigate = computed(() => {
  return tickers.value.length > 1
})

// Methods
const formatSymbol = (symbol: string) => {
  return symbol.replace('-', '/')
}

const formatPrice = (price: number) => {
  if (price >= 1000) {
    return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  } else if (price >= 1) {
    return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
  } else {
    return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 })
  }
}

const formatChange = (change: number) => {
  const sign = change >= 0 ? '+' : ''
  return `${sign}${change.toFixed(2)}%`
}

const formatVolume = (volume: number) => {
  if (volume >= 1_000_000_000) {
    return `${(volume / 1_000_000_000).toFixed(2)}B`
  } else if (volume >= 1_000_000) {
    return `${(volume / 1_000_000).toFixed(2)}M`
  } else if (volume >= 1_000) {
    return `${(volume / 1_000).toFixed(2)}K`
  } else {
    return volume.toFixed(2)
  }
}

const getPriceChangeClass = (ticker: TickerData) => {
  if (ticker.flash_direction === 'up') {
    return 'price-up'
  } else if (ticker.flash_direction === 'down') {
    return 'price-down'
  }
  return ''
}

const getChangeClass = (ticker: TickerData) => {
  return ticker.change_percentage >= 0 ? 'change-up' : 'change-down'
}

const nextTicker = () => {
  pauseAutoScroll()
  activeIndex.value = (activeIndex.value + 1) % tickers.value.length
}

const prevTicker = () => {
  pauseAutoScroll()
  activeIndex.value = (activeIndex.value - 1 + tickers.value.length) % tickers.value.length
}

const setActiveTicker = (index: number) => {
  pauseAutoScroll()
  activeIndex.value = index
}

const startAutoScroll = () => {
  if (autoScrollInterval.value) {
    clearInterval(autoScrollInterval.value)
  }
  
  isAutoScrolling.value = true
  autoScrollInterval.value = setInterval(() => {
    if (tickers.value.length > 1) {
      activeIndex.value = (activeIndex.value + 1) % tickers.value.length
    }
  }, 5000) // Auto scroll every 5 seconds
}

const pauseAutoScroll = () => {
  isAutoScrolling.value = false
  if (autoScrollInterval.value) {
    clearInterval(autoScrollInterval.value)
    autoScrollInterval.value = null
  }
  
  // Restart auto scroll after 15 seconds of inactivity
  setTimeout(() => {
    if (!isAutoScrolling.value) {
      startAutoScroll()
    }
  }, 15000)
}

// Handle WebSocket messages
const handleTickerUpdate = (data: any) => {
  try {
    if (!data || !data.symbol) return
    
    const index = tickers.value.findIndex(t => t.symbol === data.symbol)
    
    if (index !== -1) {
      const currentTicker = tickers.value[index]
      const previousPrice = currentTicker.price
      
      // Update ticker data
      tickers.value[index] = {
        ...currentTicker,
        price: data.price,
        previous_price: previousPrice,
        change_percentage: data.change_percentage || currentTicker.change_percentage,
        volume_24h: data.volume_24h || currentTicker.volume_24h,
        last_updated: new Date()
      }
      
      // Flash animation for price changes
      if (previousPrice !== data.price) {
        const direction = data.price > previousPrice ? 'up' : 'down'
        
        // Clear any existing flash timeout
        if (currentTicker.flash_timeout) {
          clearTimeout(currentTicker.flash_timeout)
        }
        
        // Set new flash direction
        tickers.value[index].flash_direction = direction
        
        // Clear flash after animation completes
        const timeout = setTimeout(() => {
          if (tickers.value[index]) {
            tickers.value[index].flash_direction = null
          }
        }, 1000)
        
        tickers.value[index].flash_timeout = timeout
      }
      
      // Reset error state if we're getting updates
      hasError.value = false
      errorMessage.value = ''
    } else if (data.symbol) {
      // Add new ticker if it doesn't exist
      tickers.value.push({
        symbol: data.symbol,
        price: data.price || 0,
        change_percentage: data.change_percentage || 0,
        volume_24h: data.volume_24h || 0,
        last_updated: new Date()
      })
    }
  } catch (err) {
    console.error('Error processing ticker update:', err)
  }
}

// Initialize WebSocket connection
const initWebSocket = () => {
  try {
    // Connect to WebSocket endpoint
    connect('/api/ws/market')
    
    // Reset error state
    hasError.value = false
    errorMessage.value = ''
  } catch (err) {
    console.error('Failed to initialize WebSocket connection:', err)
    handleConnectionError(err)
  }
}

// Handle WebSocket errors
const handleConnectionError = (err: any) => {
  hasError.value = true
  errorMessage.value = err instanceof Error 
    ? `行情数据连接失败: ${err.message}` 
    : '行情数据连接失败'
  
  // Try to reconnect after delay
  setTimeout(() => {
    if (!isConnected.value) {
      initWebSocket()
    }
  }, 5000)
}

// Lifecycle hooks
onMounted(() => {
  initWebSocket()
  startAutoScroll()
  
  // Add mock data for development if needed
  if (import.meta.env.DEV) {
    // Simulate ticker updates for development
    const mockInterval = setInterval(() => {
      if (!isConnected.value) {
        const mockData = [
          {
            symbol: 'ETH-USDT',
            price: 3500 + Math.random() * 100,
            change_percentage: 2.5 + Math.random() * 2,
            volume_24h: 1_500_000_000 + Math.random() * 100_000_000
          },
          {
            symbol: 'BTC-USDT',
            price: 65000 + Math.random() * 1000,
            change_percentage: 1.2 + Math.random() * 1,
            volume_24h: 25_000_000_000 + Math.random() * 1_000_000_000
          },
          {
            symbol: 'SOL-USDT',
            price: 120 + Math.random() * 10,
            change_percentage: -1.5 + Math.random() * 3,
            volume_24h: 800_000_000 + Math.random() * 50_000_000
          }
        ]
        
        mockData.forEach(data => handleTickerUpdate(data))
      }
    }, 3000)
    
    onBeforeUnmount(() => {
      clearInterval(mockInterval)
    })
  }
})

onBeforeUnmount(() => {
  // Clean up
  if (autoScrollInterval.value) {
    clearInterval(autoScrollInterval.value)
  }
  
  // Clean up any flash timeouts
  tickers.value.forEach(ticker => {
    if (ticker.flash_timeout) {
      clearTimeout(ticker.flash_timeout)
    }
  })
  
  // Disconnect WebSocket
  disconnect()
})

// Watch for WebSocket messages
watch(lastMessage, (newMessage) => {
  if (newMessage) {
    try {
      const data = JSON.parse(newMessage)
      if (data.type === 'ticker') {
        handleTickerUpdate(data.data)
      }
    } catch (err) {
      console.error('Failed to parse WebSocket message:', err)
    }
  }
})

// Watch for WebSocket errors
watch(wsError, (newError) => {
  if (newError) {
    handleConnectionError(newError)
  }
})

// Watch for device changes to handle responsive behavior
watch(() => device.value, (newDevice) => {
  if (newDevice === 'mobile') {
    // Pause auto-scroll when on mobile
    if (autoScrollInterval.value) {
      clearInterval(autoScrollInterval.value)
      autoScrollInterval.value = null
    }
  } else {
    // Resume auto-scroll when back to desktop
    if (!autoScrollInterval.value) {
      startAutoScroll()
    }
  }
})
</script>

<style lang="scss" scoped>
.market-ticker-container {
  position: relative;
  width: 100%;
  height: 40px;
  overflow: hidden;
  background-color: var(--el-bg-color-overlay);
  border-radius: 4px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  
  .ticker-wrapper {
    display: flex;
    align-items: center;
    width: 100%;
    height: 100%;
  }
  
  .ticker-status {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 100%;
    
    &.connected {
      color: var(--el-color-success);
    }
    
    &.error {
      color: var(--el-color-danger);
    }
  }
  
  .ticker-content {
    flex: 1;
    height: 100%;
    overflow: hidden;
    position: relative;
    
    .ticker-items {
      display: flex;
      height: 100%;
      width: 100%;
    }
    
    .ticker-item {
      display: flex;
      align-items: center;
      flex: 0 0 100%;
      padding: 0 10px;
      opacity: 0;
      transform: translateX(100%);
      transition: transform 0.5s ease, opacity 0.5s ease;
      
      &.active {
        opacity: 1;
        transform: translateX(0);
      }
      
      .ticker-symbol {
        font-weight: bold;
        margin-right: 15px;
        white-space: nowrap;
      }
      
      .ticker-price {
        font-weight: 500;
        margin-right: 15px;
        white-space: nowrap;
        transition: color 0.3s ease;
        
        &.price-up {
          color: var(--el-color-success);
          animation: flash-green 1s;
        }
        
        &.price-down {
          color: var(--el-color-danger);
          animation: flash-red 1s;
        }
      }
      
      .ticker-change {
        margin-right: 15px;
        white-space: nowrap;
        
        &.change-up {
          color: var(--el-color-success);
        }
        
        &.change-down {
          color: var(--el-color-danger);
        }
      }
      
      .ticker-volume {
        color: var(--el-text-color-secondary);
        font-size: 0.9em;
        white-space: nowrap;
      }
    }
  }
  
  .ticker-controls {
    display: flex;
    align-items: center;
    padding: 0 5px;
    
    .ticker-dots {
      display: flex;
      align-items: center;
      margin: 0 5px;
      
      .ticker-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background-color: var(--el-border-color);
        margin: 0 3px;
        cursor: pointer;
        transition: all 0.3s ease;
        
        &.active {
          width: 8px;
          height: 8px;
          background-color: var(--el-color-primary);
        }
        
        &:hover {
          background-color: var(--el-color-primary-light-3);
        }
      }
    }
  }
  
  .error-icon {
    position: absolute;
    top: 50%;
    right: 10px;
    transform: translateY(-50%);
    color: var(--el-color-danger);
    cursor: pointer;
    z-index: 10;
  }
}

// Animations
@keyframes flash-green {
  0% { background-color: rgba(103, 194, 58, 0.2); }
  100% { background-color: transparent; }
}

@keyframes flash-red {
  0% { background-color: rgba(245, 108, 108, 0.2); }
  100% { background-color: transparent; }
}

// Responsive design
@media (max-width: 992px) {
  .market-ticker-container {
    display: none;
  }
}

// Dark mode adaptations
:deep(.dark-mode) {
  .market-ticker-container {
    background-color: #1f2937;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
    
    .ticker-item {
      .ticker-symbol {
        color: #e0e0e0;
      }
      
      .ticker-volume {
        color: #a0a0a0;
      }
    }
    
    .ticker-dots {
      .ticker-dot {
        background-color: #4b5563;
        
        &.active {
          background-color: var(--el-color-primary);
        }
      }
    }
  }
  
  @keyframes flash-green {
    0% { background-color: rgba(103, 194, 58, 0.15); }
    100% { background-color: transparent; }
  }

  @keyframes flash-red {
    0% { background-color: rgba(245, 108, 108, 0.15); }
    100% { background-color: transparent; }
  }
}
</style>
