import { ref, reactive, onMounted, onBeforeUnmount, watch } from 'vue'
import { useUserStore } from '@/store/modules/user'

/**
 * WebSocket connection states
 */
export enum WebSocketState {
  CONNECTING = 'connecting',
  OPEN = 'open',
  CLOSING = 'closing',
  CLOSED = 'closed'
}

/**
 * WebSocket event types
 */
export enum WebSocketEventType {
  OPEN = 'open',
  MESSAGE = 'message',
  ERROR = 'error',
  CLOSE = 'close',
  RECONNECT = 'reconnect',
  RECONNECT_ATTEMPT = 'reconnect_attempt',
  RECONNECT_ERROR = 'reconnect_error',
  RECONNECT_FAILED = 'reconnect_failed',
  PING = 'ping',
  PONG = 'pong'
}

/**
 * WebSocket message event
 */
export interface WebSocketMessageEvent {
  type: string
  data: any
}

/**
 * WebSocket options
 */
export interface WebSocketOptions {
  url?: string
  autoConnect?: boolean
  reconnect?: boolean
  reconnectAttempts?: number
  reconnectInterval?: number
  maxReconnectInterval?: number
  reconnectDecay?: number
  timeout?: number
  heartbeatInterval?: number
  heartbeatMessage?: string | object
  protocols?: string | string[]
  onOpen?: (event: Event) => void
  onMessage?: (event: MessageEvent) => void
  onError?: (event: Event) => void
  onClose?: (event: CloseEvent) => void
}

/**
 * Default WebSocket options
 */
const defaultOptions: WebSocketOptions = {
  autoConnect: false,
  reconnect: true,
  reconnectAttempts: Infinity,
  reconnectInterval: 1000,
  maxReconnectInterval: 30000,
  reconnectDecay: 1.5,
  timeout: 20000,
  heartbeatInterval: 30000,
  heartbeatMessage: { type: 'ping' }
}

// WebSocket instance shared across the application
let globalWebSocket: WebSocket | null = null
let globalOptions: Required<WebSocketOptions>
let reconnectTimer: number | null = null
let heartbeatTimer: number | null = null
let reconnectAttempts = 0
let forceClosed = false

/**
 * Vue 3 Composable for WebSocket management
 * @param options WebSocket options
 * @returns WebSocket composable API
 */
export function useWebSocket(path?: string, options: WebSocketOptions = {}) {
  // Merge options with defaults
  const mergedOptions: Required<WebSocketOptions> = {
    ...defaultOptions,
    ...options,
    url: path ? getWebSocketUrl(path) : options.url
  }
  
  // Store options for reconnection
  globalOptions = mergedOptions
  
  // Reactive state
  const state = ref<WebSocketState>(WebSocketState.CLOSED)
  const connected = ref(false)
  const connecting = ref(false)
  const error = ref<Event | null>(null)
  const lastMessage = ref<string | null>(null)
  const reconnecting = ref(false)
  const reconnectCount = ref(0)
  
  // Message queue for when socket is not connected
  const messageQueue = reactive<(string | ArrayBufferLike | Blob | ArrayBufferView)[]>([])
  
  // Event listeners storage
  const listeners = reactive<Record<string, Function[]>>({})
  
  /**
   * Get WebSocket URL based on current environment
   * @param path WebSocket path
   * @returns Full WebSocket URL
   */
  function getWebSocketUrl(path: string): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = import.meta.env.VITE_API_BASE_URL || window.location.host
    
    // If path already starts with ws:// or wss://, return it as is
    if (path.startsWith('ws://') || path.startsWith('wss://')) {
      return path
    }
    
    // Ensure path starts with a slash
    const normalizedPath = path.startsWith('/') ? path : `/${path}`
    
    // For development environment, use the VITE_API_BASE_URL if available
    if (import.meta.env.DEV && import.meta.env.VITE_API_BASE_URL) {
      const baseUrl = import.meta.env.VITE_API_BASE_URL.replace(/^https?:\/\//, '')
      return `${protocol}//${baseUrl}${normalizedPath}`
    }
    
    return `${protocol}//${host}${normalizedPath}`
  }
  
  /**
   * Initialize WebSocket connection
   */
  function initWebSocket() {
    if (!mergedOptions.url) {
      console.error('WebSocket URL is required')
      return
    }
    
    // Clean up existing connection if any
    cleanup()
    
    try {
      connecting.value = true
      state.value = WebSocketState.CONNECTING
      
      // Create new WebSocket instance
      globalWebSocket = mergedOptions.protocols
        ? new WebSocket(mergedOptions.url, mergedOptions.protocols)
        : new WebSocket(mergedOptions.url)
      
      // Set up event listeners
      globalWebSocket.onopen = handleOpen
      globalWebSocket.onmessage = handleMessage
      globalWebSocket.onerror = handleError
      globalWebSocket.onclose = handleClose
      
      // Set connection timeout
      const connectionTimeout = window.setTimeout(() => {
        if (state.value === WebSocketState.CONNECTING) {
          handleError(new Event('timeout'))
          if (globalWebSocket) {
            globalWebSocket.close()
          }
        }
      }, mergedOptions.timeout)
      
      // Clear timeout when connected
      const clearConnectionTimeout = () => {
        window.clearTimeout(connectionTimeout)
        if (globalWebSocket) {
          globalWebSocket.removeEventListener('open', clearConnectionTimeout)
        }
      }
      
      if (globalWebSocket) {
        globalWebSocket.addEventListener('open', clearConnectionTimeout)
      }
      
    } catch (err) {
      console.error('Failed to create WebSocket instance:', err)
      handleError(new Event('error'))
    }
  }
  
  /**
   * Handle WebSocket open event
   * @param event Open event
   */
  function handleOpen(event: Event) {
    if (!globalWebSocket) return
    
    state.value = WebSocketState.OPEN
    connected.value = true
    connecting.value = false
    error.value = null
    reconnectAttempts = 0
    reconnecting.value = false
    
    // Start heartbeat
    startHeartbeat()
    
    // Process message queue
    processMessageQueue()
    
    // Call custom onOpen handler if provided
    if (mergedOptions.onOpen) {
      mergedOptions.onOpen(event)
    }
    
    // Emit open event
    emit(WebSocketEventType.OPEN, event)
  }
  
  /**
   * Handle WebSocket message event
   * @param event Message event
   */
  function handleMessage(event: MessageEvent) {
    if (!event.data) return
    
    // Update last message
    lastMessage.value = typeof event.data === 'string' 
      ? event.data 
      : JSON.stringify(event.data)
    
    // Handle heartbeat response (pong)
    if (lastMessage.value.includes('pong')) {
      emit(WebSocketEventType.PONG, event)
    }
    
    // Call custom onMessage handler if provided
    if (mergedOptions.onMessage) {
      mergedOptions.onMessage(event)
    }
    
    // Emit message event
    emit(WebSocketEventType.MESSAGE, event)
  }
  
  /**
   * Handle WebSocket error event
   * @param event Error event
   */
  function handleError(event: Event) {
    error.value = event
    
    // Call custom onError handler if provided
    if (mergedOptions.onError) {
      mergedOptions.onError(event)
    }
    
    // Emit error event
    emit(WebSocketEventType.ERROR, event)
  }
  
  /**
   * Handle WebSocket close event
   * @param event Close event
   */
  function handleClose(event: CloseEvent) {
    state.value = WebSocketState.CLOSED
    connected.value = false
    connecting.value = false
    
    // Clear heartbeat timer
    if (heartbeatTimer !== null) {
      window.clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    
    // Call custom onClose handler if provided
    if (mergedOptions.onClose) {
      mergedOptions.onClose(event)
    }
    
    // Emit close event
    emit(WebSocketEventType.CLOSE, event)
    
    // Attempt to reconnect if enabled and not forcefully closed
    if (mergedOptions.reconnect && !forceClosed) {
      reconnect()
    }
  }
  
  /**
   * Attempt to reconnect
   */
  function reconnect() {
    if (
      state.value !== WebSocketState.CLOSED ||
      reconnectTimer !== null ||
      reconnectAttempts >= mergedOptions.reconnectAttempts
    ) {
      return
    }
    
    reconnecting.value = true
    reconnectCount.value = reconnectAttempts + 1
    
    // Emit reconnect attempt event
    emit(WebSocketEventType.RECONNECT_ATTEMPT, { attempt: reconnectAttempts + 1 })
    
    // Calculate backoff delay with exponential decay
    const delay = Math.min(
      mergedOptions.reconnectInterval * Math.pow(mergedOptions.reconnectDecay, reconnectAttempts),
      mergedOptions.maxReconnectInterval
    )
    
    // Set reconnect timer
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      reconnectAttempts++
      
      try {
        initWebSocket()
      } catch (err) {
        // Emit reconnect error event
        emit(WebSocketEventType.RECONNECT_ERROR, err)
        
        // Try again if we haven't exceeded max attempts
        if (reconnectAttempts < mergedOptions.reconnectAttempts) {
          reconnect()
        } else {
          // Emit reconnect failed event
          emit(WebSocketEventType.RECONNECT_FAILED, { attempts: reconnectAttempts })
          reconnecting.value = false
        }
      }
    }, delay)
  }
  
  /**
   * Start heartbeat mechanism
   */
  function startHeartbeat() {
    if (!mergedOptions.heartbeatInterval || heartbeatTimer !== null) return
    
    heartbeatTimer = window.setInterval(() => {
      if (state.value === WebSocketState.OPEN) {
        // Send heartbeat message
        const message = typeof mergedOptions.heartbeatMessage === 'string'
          ? mergedOptions.heartbeatMessage
          : JSON.stringify(mergedOptions.heartbeatMessage)
        
        send(message)
        
        // Emit ping event
        emit(WebSocketEventType.PING, { time: Date.now() })
      }
    }, mergedOptions.heartbeatInterval)
  }
  
  /**
   * Process message queue
   */
  function processMessageQueue() {
    if (state.value !== WebSocketState.OPEN || !messageQueue.length) return
    
    // Send all queued messages
    while (messageQueue.length > 0) {
      const message = messageQueue.shift()
      if (message !== undefined && globalWebSocket) {
        globalWebSocket.send(message)
      }
    }
  }
  
  /**
   * Connect to WebSocket server
   * @param url Optional URL to override the default
   */
  function connect(url?: string) {
    if (url) {
      mergedOptions.url = getWebSocketUrl(url)
    }
    
    if (!mergedOptions.url) {
      throw new Error('WebSocket URL is required')
    }
    
    forceClosed = false
    
    if (state.value === WebSocketState.OPEN) {
      console.warn('WebSocket is already connected')
      return
    }
    
    initWebSocket()
  }
  
  /**
   * Disconnect from WebSocket server
   * @param code Close code
   * @param reason Close reason
   */
  function disconnect(code?: number, reason?: string) {
    if (!globalWebSocket) return
    
    forceClosed = true
    
    if (state.value === WebSocketState.OPEN || state.value === WebSocketState.CONNECTING) {
      state.value = WebSocketState.CLOSING
      globalWebSocket.close(code, reason)
    }
    
    cleanup()
  }
  
  /**
   * Send message to WebSocket server
   * @param data Message data
   * @param useQueue Whether to queue message if not connected
   * @returns Whether the message was sent or queued
   */
  function send(
    data: string | ArrayBufferLike | Blob | ArrayBufferView,
    useQueue: boolean = true
  ): boolean {
    // If not connected and queuing is enabled, add to queue
    if (state.value !== WebSocketState.OPEN) {
      if (useQueue) {
        messageQueue.push(data)
        return true
      }
      return false
    }
    
    // Send message if connected
    if (globalWebSocket) {
      try {
        globalWebSocket.send(data)
        return true
      } catch (err) {
        console.error('Failed to send WebSocket message:', err)
        return false
      }
    }
    
    return false
  }
  
  /**
   * Send JSON message to WebSocket server
   * @param data JSON data
   * @param useQueue Whether to queue message if not connected
   * @returns Whether the message was sent or queued
   */
  function sendJson(data: any, useQueue: boolean = true): boolean {
    try {
      const jsonString = JSON.stringify(data)
      return send(jsonString, useQueue)
    } catch (err) {
      console.error('Failed to stringify JSON data:', err)
      return false
    }
  }
  
  /**
   * Add event listener
   * @param type Event type
   * @param handler Event handler
   */
  function on(type: string, handler: Function): void {
    if (!listeners[type]) {
      listeners[type] = []
    }
    listeners[type].push(handler)
  }
  
  /**
   * Remove event listener
   * @param type Event type
   * @param handler Event handler
   */
  function off(type: string, handler?: Function): void {
    if (!listeners[type]) return
    
    if (!handler) {
      // Remove all listeners of this type
      delete listeners[type]
    } else {
      // Remove specific handler
      const index = listeners[type].indexOf(handler)
      if (index !== -1) {
        listeners[type].splice(index, 1)
      }
      
      // Clean up empty listener arrays
      if (listeners[type].length === 0) {
        delete listeners[type]
      }
    }
  }
  
  /**
   * Emit event to listeners
   * @param type Event type
   * @param data Event data
   */
  function emit(type: string, data?: any): void {
    if (!listeners[type]) return
    
    for (const handler of listeners[type]) {
      try {
        handler(data)
      } catch (err) {
        console.error(`Error in WebSocket ${type} event handler:`, err)
      }
    }
  }
  
  /**
   * Clean up WebSocket resources
   */
  function cleanup(): void {
    // Clear timers
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    
    if (heartbeatTimer !== null) {
      window.clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    
    // Remove event listeners from existing WebSocket
    if (globalWebSocket) {
      globalWebSocket.onopen = null
      globalWebSocket.onmessage = null
      globalWebSocket.onerror = null
      globalWebSocket.onclose = null
      
      // Close connection if still open
      if (globalWebSocket.readyState === WebSocket.OPEN || 
          globalWebSocket.readyState === WebSocket.CONNECTING) {
        try {
          globalWebSocket.close()
        } catch (err) {
          console.error('Error closing WebSocket:', err)
        }
      }
      
      globalWebSocket = null
    }
    
    // Reset state
    state.value = WebSocketState.CLOSED
    connected.value = false
    connecting.value = false
    reconnecting.value = false
  }
  
  // Auto-connect if enabled
  if (mergedOptions.autoConnect && mergedOptions.url) {
    // Use nextTick or setTimeout to ensure Vue instance is fully initialized
    setTimeout(() => {
      connect()
    }, 0)
  }
  
  // Watch for authentication changes
  const userStore = useUserStore()
  watch(() => userStore.token, (newToken) => {
    // Reconnect with new auth token if connection was previously established
    if (newToken && (state.value === WebSocketState.CLOSED || state.value === WebSocketState.CLOSING)) {
      connect()
    }
  })
  
  // Lifecycle hooks for automatic cleanup
  onBeforeUnmount(() => {
    cleanup()
  })
  
  // Return public API
  return {
    // State
    state,
    connected,
    connecting,
    reconnecting,
    reconnectCount,
    error,
    lastMessage,
    
    // Methods
    connect,
    disconnect,
    send,
    sendJson,
    on,
    off,
    
    // Raw access (use with caution)
    getWebSocket: () => globalWebSocket
  }
}

// Create a singleton instance for global usage
export const globalWebSocketInstance = useWebSocket()
