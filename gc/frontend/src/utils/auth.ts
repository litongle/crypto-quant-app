import CryptoJS from 'crypto-js'

// Token storage keys
const TOKEN_KEY = 'access_token'
const REFRESH_TOKEN_KEY = 'refresh_token'
const TOKEN_EXPIRES_KEY = 'token_expires'

/**
 * Token data interfaces
 */
export interface TokenPayload {
  // Standard JWT claims
  iss?: string       // Issuer
  sub?: string       // Subject (usually user ID)
  aud?: string[]     // Audience
  exp?: number       // Expiration time (unix timestamp)
  nbf?: number       // Not before (unix timestamp)
  iat?: number       // Issued at (unix timestamp)
  jti?: string       // JWT ID
  
  // Custom claims
  user_id?: number
  username?: string
  roles?: string[]
  permissions?: string[]
  [key: string]: any // Allow any additional properties
}

export interface TokenResponse {
  token: string
  refresh_token?: string
  expires_in?: number
  token_type?: string
}

/**
 * Get token from localStorage
 * @returns The stored token or null if not found
 */
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

/**
 * Set token in localStorage
 * @param token The token to store
 */
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

/**
 * Remove token from localStorage
 */
export function removeToken(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(TOKEN_EXPIRES_KEY)
}

/**
 * Get refresh token from localStorage
 * @returns The stored refresh token or null if not found
 */
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

/**
 * Set refresh token in localStorage
 * @param token The refresh token to store
 */
export function setRefreshToken(token: string): void {
  localStorage.setItem(REFRESH_TOKEN_KEY, token)
}

/**
 * Remove refresh token from localStorage
 */
export function removeRefreshToken(): void {
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

/**
 * Set token expiration timestamp in localStorage
 * @param timestamp The expiration timestamp (unix timestamp in milliseconds)
 */
export function setTokenExpiration(timestamp: number): void {
  localStorage.setItem(TOKEN_EXPIRES_KEY, timestamp.toString())
}

/**
 * Get token expiration timestamp from localStorage
 * @returns The expiration timestamp or 0 if not found
 */
export function getTokenExpiration(): number {
  const expires = localStorage.getItem(TOKEN_EXPIRES_KEY)
  return expires ? parseInt(expires, 10) : 0
}

/**
 * Check if token is expired
 * @param expirationTime The expiration timestamp to check (optional, uses stored value if not provided)
 * @returns True if token is expired or expiration time is invalid
 */
export function isTokenExpired(expirationTime?: number): boolean {
  const expiration = expirationTime || getTokenExpiration()
  if (!expiration) return true
  
  // Add a small buffer (10 seconds) to account for network latency
  return Date.now() >= expiration - 10000
}

/**
 * Calculate time remaining until token expires
 * @param expirationTime The expiration timestamp (optional, uses stored value if not provided)
 * @returns Time in milliseconds until expiration, or 0 if already expired
 */
export function getTimeUntilExpiration(expirationTime?: number): number {
  const expiration = expirationTime || getTokenExpiration()
  if (!expiration) return 0
  
  const timeRemaining = expiration - Date.now()
  return timeRemaining > 0 ? timeRemaining : 0
}

/**
 * Decode JWT token without verification
 * @param token The JWT token to decode
 * @returns The decoded token payload or null if invalid
 */
export function decodeToken(token: string): TokenPayload | null {
  try {
    // JWT format: header.payload.signature
    const parts = token.split('.')
    if (parts.length !== 3) return null
    
    // Base64Url decode the payload
    const payload = parts[1]
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    )
    
    return JSON.parse(jsonPayload)
  } catch (error) {
    console.error('Failed to decode token:', error)
    return null
  }
}

/**
 * Extract user information from token
 * @param token The JWT token
 * @returns User information from token or null if invalid
 */
export function extractUserFromToken(token: string): { 
  userId: number | null,
  username: string,
  roles: string[]
} | null {
  const decoded = decodeToken(token)
  if (!decoded) return null
  
  return {
    userId: decoded.user_id || null,
    username: decoded.username || '',
    roles: decoded.roles || []
  }
}

/**
 * Hash a password (client-side only, for demonstration)
 * Note: Real password hashing should be done server-side
 * @param password The password to hash
 * @returns Hashed password
 */
export function hashPassword(password: string): string {
  return CryptoJS.SHA256(password).toString()
}

/**
 * Generate a random security token
 * @param length The length of the token (default: 32)
 * @returns Random security token
 */
export function generateSecurityToken(length: number = 32): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  let result = ''
  
  // Use crypto API if available for better randomness
  if (window.crypto && window.crypto.getRandomValues) {
    const values = new Uint32Array(length)
    window.crypto.getRandomValues(values)
    for (let i = 0; i < length; i++) {
      result += chars[values[i] % chars.length]
    }
  } else {
    // Fallback to Math.random
    for (let i = 0; i < length; i++) {
      result += chars.charAt(Math.floor(Math.random() * chars.length))
    }
  }
  
  return result
}

/**
 * Encrypt sensitive data
 * @param data The data to encrypt
 * @param key The encryption key (optional)
 * @returns Encrypted data
 */
export function encryptData(data: string, key?: string): string {
  const encryptionKey = key || import.meta.env.VITE_ENCRYPTION_KEY || 'default-encryption-key'
  return CryptoJS.AES.encrypt(data, encryptionKey).toString()
}

/**
 * Decrypt sensitive data
 * @param encryptedData The data to decrypt
 * @param key The encryption key (optional)
 * @returns Decrypted data or empty string if decryption fails
 */
export function decryptData(encryptedData: string, key?: string): string {
  try {
    const encryptionKey = key || import.meta.env.VITE_ENCRYPTION_KEY || 'default-encryption-key'
    const bytes = CryptoJS.AES.decrypt(encryptedData, encryptionKey)
    return bytes.toString(CryptoJS.enc.Utf8)
  } catch (error) {
    console.error('Failed to decrypt data:', error)
    return ''
  }
}

/**
 * Store authentication data securely
 * @param tokenData The token data to store
 */
export function storeAuthData(tokenData: TokenResponse): void {
  if (tokenData.token) {
    setToken(tokenData.token)
    
    // Extract expiration from token if not provided in response
    const decoded = decodeToken(tokenData.token)
    if (decoded && decoded.exp) {
      setTokenExpiration(decoded.exp * 1000) // Convert to milliseconds
    } else if (tokenData.expires_in) {
      setTokenExpiration(Date.now() + tokenData.expires_in * 1000)
    }
    
    if (tokenData.refresh_token) {
      setRefreshToken(tokenData.refresh_token)
    }
  }
}

/**
 * Clear all authentication data
 */
export function clearAuthData(): void {
  removeToken()
  removeRefreshToken()
  localStorage.removeItem(TOKEN_EXPIRES_KEY)
}

/**
 * Check if user is authenticated
 * @returns True if user has a valid, non-expired token
 */
export function isAuthenticated(): boolean {
  const token = getToken()
  return !!token && !isTokenExpired()
}
