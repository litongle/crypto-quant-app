/**
 * Validation Utilities
 * 
 * This file contains validation functions for various data types and formats
 * used throughout the application.
 */

// ===== URL Validation =====

/**
 * Check if a string is a valid URL
 * @param url The URL to validate
 * @returns True if the URL is valid
 */
export function isValidUrl(url: string): boolean {
  try {
    new URL(url)
    return true
  } catch (err) {
    return false
  }
}

/**
 * Check if a URL is external (not same origin)
 * @param url The URL to check
 * @returns True if the URL is external
 */
export function isExternal(url: string): boolean {
  if (!url) return false
  
  // Handle special cases
  if (url.startsWith('mailto:') || 
      url.startsWith('tel:') || 
      url.startsWith('sms:')) {
    return true
  }
  
  // Check if it's a valid URL
  try {
    const urlObj = new URL(url, window.location.origin)
    return urlObj.hostname !== window.location.hostname
  } catch (err) {
    // If it's not a valid URL, it's not external
    return false
  }
}

/**
 * Check if a path is an absolute path
 * @param path The path to check
 * @returns True if the path is absolute
 */
export function isAbsolutePath(path: string): boolean {
  return /^\/([^/]|$)/.test(path)
}

// ===== Email Validation =====

/**
 * Check if a string is a valid email address
 * @param email The email to validate
 * @returns True if the email is valid
 */
export function isValidEmail(email: string): boolean {
  // RFC 5322 compliant email regex
  const emailRegex = /^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/
  return emailRegex.test(email)
}

// ===== Phone Number Validation =====

/**
 * Check if a string is a valid phone number
 * Supports international formats with or without country code
 * @param phone The phone number to validate
 * @returns True if the phone number is valid
 */
export function isValidPhone(phone: string): boolean {
  // Basic phone validation (supports international formats)
  // Allows formats like: +1 123-456-7890, (123) 456-7890, 123.456.7890, etc.
  const phoneRegex = /^(\+?\d{1,3}[- ]?)?\(?(\d{3})\)?[- ]?(\d{3})[- ]?(\d{4})$/
  return phoneRegex.test(phone)
}

/**
 * Check if a string is a valid Chinese phone number
 * @param phone The phone number to validate
 * @returns True if the phone number is valid
 */
export function isValidChinesePhone(phone: string): boolean {
  // Chinese mobile phone number validation
  const cnPhoneRegex = /^((\+|00)86)?1([3-9][0-9])\d{8}$/
  return cnPhoneRegex.test(phone)
}

// ===== Password Validation =====

/**
 * Password strength levels
 */
export enum PasswordStrength {
  WEAK = 'weak',
  MEDIUM = 'medium',
  STRONG = 'strong',
  VERY_STRONG = 'very_strong'
}

/**
 * Check password strength
 * @param password The password to check
 * @returns Password strength level
 */
export function checkPasswordStrength(password: string): PasswordStrength {
  if (!password || password.length < 8) {
    return PasswordStrength.WEAK
  }
  
  let score = 0
  
  // Length check
  if (password.length >= 12) score += 2
  else if (password.length >= 8) score += 1
  
  // Character variety checks
  if (/[A-Z]/.test(password)) score += 1 // Has uppercase
  if (/[a-z]/.test(password)) score += 1 // Has lowercase
  if (/[0-9]/.test(password)) score += 1 // Has number
  if (/[^A-Za-z0-9]/.test(password)) score += 2 // Has special char
  
  // Complexity checks
  if (/(.)\1{2,}/.test(password)) score -= 1 // Penalize repeating characters
  if (/^(?=.*[A-Z])(?=.*[a-z])(?=.*[0-9])(?=.*[^A-Za-z0-9]).{10,}$/.test(password)) {
    score += 2 // Bonus for having all character types and length >= 10
  }
  
  // Common patterns check
  if (/password|123456|qwerty|admin/i.test(password)) score -= 2
  
  // Determine strength based on score
  if (score >= 6) return PasswordStrength.VERY_STRONG
  if (score >= 4) return PasswordStrength.STRONG
  if (score >= 2) return PasswordStrength.MEDIUM
  return PasswordStrength.WEAK
}

/**
 * Check if a password meets minimum requirements
 * @param password The password to check
 * @param minLength Minimum required length (default: 8)
 * @param requireUppercase Require at least one uppercase letter
 * @param requireLowercase Require at least one lowercase letter
 * @param requireNumber Require at least one number
 * @param requireSpecial Require at least one special character
 * @returns True if the password meets all requirements
 */
export function isValidPassword(
  password: string,
  minLength: number = 8,
  requireUppercase: boolean = true,
  requireLowercase: boolean = true,
  requireNumber: boolean = true,
  requireSpecial: boolean = true
): boolean {
  if (!password || password.length < minLength) return false
  
  if (requireUppercase && !/[A-Z]/.test(password)) return false
  if (requireLowercase && !/[a-z]/.test(password)) return false
  if (requireNumber && !/[0-9]/.test(password)) return false
  if (requireSpecial && !/[^A-Za-z0-9]/.test(password)) return false
  
  return true
}

// ===== Common Form Field Validation =====

/**
 * Check if a string is empty (null, undefined, or only whitespace)
 * @param value The string to check
 * @returns True if the string is empty
 */
export function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.keys(value).length === 0
  return false
}

/**
 * Check if a string is within a specified length range
 * @param str The string to check
 * @param min Minimum length (inclusive)
 * @param max Maximum length (inclusive)
 * @returns True if the string length is within range
 */
export function isLengthInRange(str: string, min: number, max: number): boolean {
  if (!str) return min === 0
  return str.length >= min && str.length <= max
}

/**
 * Check if a value is a valid number
 * @param value The value to check
 * @returns True if the value is a valid number
 */
export function isNumber(value: unknown): boolean {
  if (typeof value === 'number') return !isNaN(value)
  if (typeof value === 'string') {
    return !isNaN(Number(value)) && value.trim() !== ''
  }
  return false
}

/**
 * Check if a value is a valid integer
 * @param value The value to check
 * @returns True if the value is a valid integer
 */
export function isInteger(value: unknown): boolean {
  if (typeof value === 'number') return Number.isInteger(value)
  if (typeof value === 'string') {
    const num = Number(value)
    return !isNaN(num) && Number.isInteger(num) && value.trim() !== ''
  }
  return false
}

/**
 * Check if a value is within a numeric range
 * @param value The value to check
 * @param min Minimum value (inclusive)
 * @param max Maximum value (inclusive)
 * @returns True if the value is within range
 */
export function isInRange(value: number, min: number, max: number): boolean {
  return value >= min && value <= max
}

/**
 * Check if a string contains only alphanumeric characters
 * @param str The string to check
 * @returns True if the string is alphanumeric
 */
export function isAlphanumeric(str: string): boolean {
  return /^[a-zA-Z0-9]+$/.test(str)
}

/**
 * Check if a string matches a specific regex pattern
 * @param str The string to check
 * @param pattern The regex pattern to match
 * @returns True if the string matches the pattern
 */
export function matchesPattern(str: string, pattern: RegExp): boolean {
  return pattern.test(str)
}

/**
 * Check if a date is valid
 * @param date The date to check (Date object or string)
 * @returns True if the date is valid
 */
export function isValidDate(date: Date | string): boolean {
  if (!date) return false
  
  const d = date instanceof Date ? date : new Date(date)
  return !isNaN(d.getTime())
}

/**
 * Check if a date is in the future
 * @param date The date to check (Date object or string)
 * @returns True if the date is in the future
 */
export function isFutureDate(date: Date | string): boolean {
  if (!isValidDate(date)) return false
  
  const d = date instanceof Date ? date : new Date(date)
  return d.getTime() > Date.now()
}

/**
 * Check if a date is in the past
 * @param date The date to check (Date object or string)
 * @returns True if the date is in the past
 */
export function isPastDate(date: Date | string): boolean {
  if (!isValidDate(date)) return false
  
  const d = date instanceof Date ? date : new Date(date)
  return d.getTime() < Date.now()
}

// ===== Trading Specific Validation =====

/**
 * Check if a value is a valid price
 * @param price The price to validate
 * @param minPrice Minimum allowed price (default: 0)
 * @param maxPrice Maximum allowed price (default: Infinity)
 * @param allowZero Whether to allow zero as a valid price
 * @returns True if the price is valid
 */
export function isValidPrice(
  price: number | string,
  minPrice: number = 0,
  maxPrice: number = Infinity,
  allowZero: boolean = false
): boolean {
  const numPrice = typeof price === 'string' ? parseFloat(price) : price
  
  if (isNaN(numPrice)) return false
  if (numPrice < 0) return false
  if (numPrice === 0 && !allowZero) return false
  
  return numPrice >= minPrice && numPrice <= maxPrice
}

/**
 * Check if a value is a valid trading quantity
 * @param quantity The quantity to validate
 * @param minQty Minimum allowed quantity (default: 0)
 * @param maxQty Maximum allowed quantity (default: Infinity)
 * @param allowZero Whether to allow zero as a valid quantity
 * @returns True if the quantity is valid
 */
export function isValidQuantity(
  quantity: number | string,
  minQty: number = 0,
  maxQty: number = Infinity,
  allowZero: boolean = false
): boolean {
  const numQty = typeof quantity === 'string' ? parseFloat(quantity) : quantity
  
  if (isNaN(numQty)) return false
  if (numQty < 0) return false
  if (numQty === 0 && !allowZero) return false
  
  return numQty >= minQty && numQty <= maxQty
}

/**
 * Check if a value is a valid leverage value
 * @param leverage The leverage to validate
 * @param minLeverage Minimum allowed leverage (default: 1)
 * @param maxLeverage Maximum allowed leverage (default: 125)
 * @returns True if the leverage is valid
 */
export function isValidLeverage(
  leverage: number | string,
  minLeverage: number = 1,
  maxLeverage: number = 125
): boolean {
  const numLeverage = typeof leverage === 'string' ? parseFloat(leverage) : leverage
  
  if (isNaN(numLeverage)) return false
  if (numLeverage <= 0) return false
  
  return numLeverage >= minLeverage && numLeverage <= maxLeverage
}

/**
 * Check if a string is a valid trading pair symbol
 * @param symbol The symbol to validate (e.g., "BTC-USDT", "ETH/USDT")
 * @returns True if the symbol is valid
 */
export function isValidTradingSymbol(symbol: string): boolean {
  // Supports formats like "BTC-USDT", "BTC/USDT", "BTCUSDT"
  return /^[A-Za-z0-9]+(-|\/)?[A-Za-z0-9]+$/.test(symbol)
}

/**
 * Check if a value is a valid stop loss price
 * @param stopLoss The stop loss price to validate
 * @param entryPrice The entry price for comparison
 * @param isLong Whether the position is long (true) or short (false)
 * @returns True if the stop loss is valid for the position type
 */
export function isValidStopLoss(
  stopLoss: number,
  entryPrice: number,
  isLong: boolean
): boolean {
  if (isNaN(stopLoss) || isNaN(entryPrice)) return false
  if (stopLoss <= 0 || entryPrice <= 0) return false
  
  // For long positions, stop loss should be below entry price
  // For short positions, stop loss should be above entry price
  return isLong ? stopLoss < entryPrice : stopLoss > entryPrice
}

/**
 * Check if a value is a valid take profit price
 * @param takeProfit The take profit price to validate
 * @param entryPrice The entry price for comparison
 * @param isLong Whether the position is long (true) or short (false)
 * @returns True if the take profit is valid for the position type
 */
export function isValidTakeProfit(
  takeProfit: number,
  entryPrice: number,
  isLong: boolean
): boolean {
  if (isNaN(takeProfit) || isNaN(entryPrice)) return false
  if (takeProfit <= 0 || entryPrice <= 0) return false
  
  // For long positions, take profit should be above entry price
  // For short positions, take profit should be below entry price
  return isLong ? takeProfit > entryPrice : takeProfit < entryPrice
}

/**
 * Check if a value is a valid percentage
 * @param value The value to check
 * @param allowNegative Whether to allow negative percentages
 * @returns True if the value is a valid percentage
 */
export function isValidPercentage(
  value: number | string,
  allowNegative: boolean = false
): boolean {
  const numValue = typeof value === 'string' ? parseFloat(value) : value
  
  if (isNaN(numValue)) return false
  if (!allowNegative && numValue < 0) return false
  
  return true
}

// ===== API Key Validation =====

/**
 * Check if a string is a valid OKX API key
 * @param apiKey The API key to validate
 * @returns True if the API key is valid
 */
export function isValidOkxApiKey(apiKey: string): boolean {
  // OKX API keys are typically 32 characters long and alphanumeric
  return /^[a-zA-Z0-9]{32}$/.test(apiKey)
}

/**
 * Check if a string is a valid OKX API secret
 * @param apiSecret The API secret to validate
 * @returns True if the API secret is valid
 */
export function isValidOkxApiSecret(apiSecret: string): boolean {
  // OKX API secrets are typically 32 characters long and alphanumeric
  return /^[a-zA-Z0-9]{32}$/.test(apiSecret)
}

/**
 * Check if a string is a valid OKX passphrase
 * @param passphrase The passphrase to validate
 * @returns True if the passphrase is valid
 */
export function isValidOkxPassphrase(passphrase: string): boolean {
  // OKX passphrases must be between 1-60 characters
  return passphrase.length >= 1 && passphrase.length <= 60
}

/**
 * Check if a string is a valid API key (generic)
 * @param apiKey The API key to validate
 * @param minLength Minimum length (default: 8)
 * @param maxLength Maximum length (default: 128)
 * @returns True if the API key is valid
 */
export function isValidApiKey(
  apiKey: string,
  minLength: number = 8,
  maxLength: number = 128
): boolean {
  if (!apiKey) return false
  if (apiKey.length < minLength || apiKey.length > maxLength) return false
  
  // Most API keys are alphanumeric, sometimes with hyphens or underscores
  return /^[a-zA-Z0-9_-]+$/.test(apiKey)
}

// ===== TypeScript Type Guards =====

/**
 * Type guard to check if a value is a string
 * @param value The value to check
 * @returns True if the value is a string
 */
export function isString(value: unknown): value is string {
  return typeof value === 'string'
}

/**
 * Type guard to check if a value is a number
 * @param value The value to check
 * @returns True if the value is a number
 */
export function isNumberType(value: unknown): value is number {
  return typeof value === 'number' && !isNaN(value)
}

/**
 * Type guard to check if a value is a boolean
 * @param value The value to check
 * @returns True if the value is a boolean
 */
export function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean'
}

/**
 * Type guard to check if a value is an array
 * @param value The value to check
 * @returns True if the value is an array
 */
export function isArray(value: unknown): value is unknown[] {
  return Array.isArray(value)
}

/**
 * Type guard to check if a value is an object
 * @param value The value to check
 * @returns True if the value is an object (not null and not an array)
 */
export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Type guard to check if a value is a Date object
 * @param value The value to check
 * @returns True if the value is a valid Date object
 */
export function isDate(value: unknown): value is Date {
  return value instanceof Date && !isNaN(value.getTime())
}

/**
 * Type guard to check if a value is a function
 * @param value The value to check
 * @returns True if the value is a function
 */
// eslint-disable-next-line @typescript-eslint/ban-types
export function isFunction(value: unknown): value is Function {
  return typeof value === 'function'
}

/**
 * Type guard to check if a value is undefined
 * @param value The value to check
 * @returns True if the value is undefined
 */
export function isUndefined(value: unknown): value is undefined {
  return typeof value === 'undefined'
}

/**
 * Type guard to check if a value is null
 * @param value The value to check
 * @returns True if the value is null
 */
export function isNull(value: unknown): value is null {
  return value === null
}

/**
 * Type guard to check if a value is null or undefined
 * @param value The value to check
 * @returns True if the value is null or undefined
 */
export function isNullOrUndefined(value: unknown): value is null | undefined {
  return value === null || typeof value === 'undefined'
}

/**
 * Type guard for a generic interface
 * @param value The value to check
 * @param properties Array of property names that should exist on the object
 * @returns True if the value has all the specified properties
 */
export function hasProperties<T>(
  value: unknown,
  properties: (keyof T)[]
): value is T {
  if (!isObject(value)) return false
  
  return properties.every(prop => 
    Object.prototype.hasOwnProperty.call(value, prop)
  )
}

/**
 * Type guard for Record<string, unknown>
 * @param value The value to check
 * @returns True if the value is a Record<string, unknown>
 */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return isObject(value)
}

/**
 * Type guard for Record<string, string>
 * @param value The value to check
 * @returns True if the value is a Record<string, string>
 */
export function isStringRecord(value: unknown): value is Record<string, string> {
  if (!isObject(value)) return false
  
  return Object.values(value).every(v => typeof v === 'string')
}
