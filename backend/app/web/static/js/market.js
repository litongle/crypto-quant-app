/**
 * 行情页面逻辑 v1 — 实时价格 + K线 + WebSocket
 */

/* 默认关注的交易对 */
const DEFAULT_WATCHLIST = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'DOGEUSDT'];

/* 当前选中的交易对和K线周期 */
let marketSymbol = 'BTCUSDT';
let marketInterval = '1h';
let marketExchange = 'binance';
let marketType = 'spot';   // F1: 'spot' | 'perp'
let marketChartType = 'candle';  // 'candle' | 'line'
let marketLastKlines = [];        // 缓存最近一次 klines,切换图表类型时复用
let marketWs = null;
let marketWsReconnectTimer = null;
let marketWsLastMessageAt = 0;
let marketWsWatchdogTimer = null;
let marketPollingTimer = null;
let marketOrderbookTimer = null;
let marketViewVersion = 0;
let marketWsSessionId = 0;
let marketIntervalCapabilities = null;
const marketIntervalCapabilitiesCache = new Map();

const MARKET_WS_STALE_MS = 8000;
const MARKET_POLL_INTERVAL_MS = 3000;
const MARKET_ORDERBOOK_INTERVAL_MS = 5000;

function getMarketContext() {
  return {
    version: marketViewVersion,
    symbol: marketSymbol,
    interval: marketInterval,
    exchange: marketExchange,
    marketType,
  };
}

function isCurrentMarketContext(ctx) {
  return !!ctx
    && ctx.version === marketViewVersion
    && ctx.symbol === marketSymbol
    && ctx.interval === marketInterval
    && ctx.exchange === marketExchange
    && ctx.marketType === marketType;
}

function invalidateMarketContext() {
  marketViewVersion += 1;
  return getMarketContext();
}

function getMarketIntervalCapabilityKey(exchange = marketExchange, type = marketType) {
  return `${exchange}:${type}`;
}

function getSupportedMarketIntervals() {
  return (marketIntervalCapabilities?.intervals || []).map(item => item.value);
}

function renderMarketIntervalControls(capabilities = marketIntervalCapabilities) {
  const container = document.getElementById('market-interval-controls');
  if (!container) return;

  const intervals = capabilities?.intervals || [];
  if (intervals.length === 0) {
    container.innerHTML = '';
    return;
  }

  const featured = new Set(capabilities?.featured_intervals || []);
  const featuredItems = intervals.filter(item => featured.has(item.value));
  const moreItems = intervals.filter(item => !featured.has(item.value));
  const moreValue = moreItems.some(item => item.value === marketInterval) ? marketInterval : '';

  const featuredHtml = featuredItems.map(item => `
    <button
      class="cq-interval-btn${item.value === marketInterval ? ' is-active' : ''}"
      data-interval="${item.value}"
      onclick="changeMarketInterval('${item.value}')"
      title="${escapeHtml(item.label)}"
    >${escapeHtml(item.shortLabel || item.value)}</button>
  `).join('');

  const moreHtml = moreItems.length > 0
    ? `
      <select id="market-interval-more" class="cq-input cq-interval-select" onchange="handleMarketIntervalSelect(this.value)" title="更多周期">
        <option value="">更多</option>
        ${moreItems.map(item => `<option value="${item.value}"${item.value === moreValue ? ' selected' : ''}>${escapeHtml(item.label)}</option>`).join('')}
      </select>
    `
    : '';

  container.innerHTML = `${featuredHtml}${moreHtml}`;
}

function handleMarketIntervalSelect(interval) {
  if (!interval) return;
  changeMarketInterval(interval);
}

async function syncMarketIntervalCapabilities() {
  const ctx = getMarketContext();
  const key = getMarketIntervalCapabilityKey(ctx.exchange, ctx.marketType);
  let capabilities = marketIntervalCapabilitiesCache.get(key);

  if (!capabilities) {
    capabilities = await api.getMarketIntervals(ctx.exchange, ctx.marketType);
    if (!isCurrentMarketContext(ctx)) return null;
    marketIntervalCapabilitiesCache.set(key, capabilities);
  }

  if (!isCurrentMarketContext(ctx)) return null;

  marketIntervalCapabilities = capabilities;
  const supported = new Set(getSupportedMarketIntervals());
  if (!supported.has(marketInterval)) {
    marketInterval = capabilities.default_interval || capabilities.defaultInterval || capabilities.intervals?.[0]?.value || '1h';
  }
  renderMarketIntervalControls(capabilities);
  return capabilities;
}

async function loadMarketPage() {
  if (typeof preloadSymbolSelectorData === 'function') {
    await preloadSymbolSelectorData();
  }

  // 渲染头部行情概览卡片
  try {
    const tickers = await api.getBatchTickers();
    renderMarketOverview(tickers);
  } catch {
    renderMarketOverview([]);
  }

  await syncMarketIntervalCapabilities();

  // 加载K线图
  await loadMarketKline();
  await loadMarketOrderbook();

  // 立即拉一次实时价格,避免首次进页面卡在 "-- --"
  refreshLivePriceNow();

  // 启动 WebSocket
  startMarketWs();
  startMarketOrderbookPolling(false);

  // 初始化交易对选择器
  initMarketSymbolSelector();
}

/* ── 行情概览卡片 ── */
function renderMarketOverview(tickers) {
  const el = document.getElementById('market-overview');
  if (!tickers || tickers.length === 0) {
    el.innerHTML = '<div class="cq-card cq-empty-state" style="padding:var(--cq-space-6);"><h3>暂无行情数据</h3><p>请检查网络连接</p></div>';
    updateMarketOverviewMeta(null);
    return;
  }
  updateMarketOverviewMeta(new Date());

  el.innerHTML = tickers.map(t => {
    const change = t.changePercent24h ?? 0;
    const isUp = change >= 0;
    const base = t.symbol.replace('USDT', '');
    const sparkSvg = renderSparkline(t.sparkline || [], isUp);

    return `
    <div class="cq-card cq-ticker-card${marketSymbol === t.symbol ? ' is-active' : ''}" onclick="selectMarketSymbol('${t.symbol}')">
      <div class="cq-ticker-card__header">
        <span class="cq-ticker-card__base">${escapeHtml(base)}</span>
        <span class="cq-ticker-card__quote">/USDT</span>
      </div>
      <div class="cq-ticker-card__price cq-num" id="ticker-price-${t.symbol}">$${formatTickerPrice(t.price)}</div>
      <div class="cq-ticker-card__change" style="color:${isUp ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">
        ${isUp ? '+' : ''}${change.toFixed(2)}%
      </div>
      <div class="cq-ticker-card__spark">${sparkSvg}</div>
    </div>`;
  }).join('');
}

/* 概览卡数据时间戳 — 显示最近一次行情更新时间 */
function updateMarketOverviewMeta(date) {
  const meta = document.getElementById('market-overview-meta');
  if (!meta) return;
  if (!date) { meta.textContent = ''; return; }
  const h = String(date.getHours()).padStart(2, '0');
  const m = String(date.getMinutes()).padStart(2, '0');
  const s = String(date.getSeconds()).padStart(2, '0');
  meta.textContent = `数据更新于 ${h}:${m}:${s}`;
}

/* 迷你趋势线 SVG */
function renderSparkline(data, isUp) {
  if (!data || data.length < 2) return '';
  const w = 64, h = 24;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const color = isUp ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)';
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function formatTickerPrice(price) {
  if (price == null || isNaN(price)) return '--';
  if (price >= 1000) return Number(price).toLocaleString('en-US', { maximumFractionDigits: 2 });
  if (price >= 1) return Number(price).toFixed(2);
  return Number(price).toFixed(4);
}

/**
 * 立即用 REST 拉一次 ticker 填进实时价格区,避免切 symbol 后等 WS 那 1-2 秒
 * 卡在 "-- --"。WS 推消息后会再覆盖一次,无需等待。
 */
async function refreshLivePriceNow() {
  const ctx = getMarketContext();
  try {
    const t = await api.getTicker(ctx.symbol, ctx.exchange, ctx.marketType, true);
    if (!isCurrentMarketContext(ctx)) return;
    applyTickerSnapshot(ctx.symbol, t, ctx);
  } catch (e) {
    // 拿不到就让 WS 兜底,什么都不做
  }
}

function applyTickerSnapshot(symbol, ticker, ctx = null) {
  const t = ticker || {};
  const activeCtx = ctx || getMarketContext();
  updateMarketOverviewMeta(new Date());

  const priceEl = document.getElementById(`ticker-price-${symbol}`);
  if (priceEl) {
    const rawPrice = t.price ?? t.lastPrice ?? t.last;
    if (rawPrice != null) {
      priceEl.textContent = '$' + formatTickerPrice(rawPrice);
      priceEl.classList.add('cq-flash');
      setTimeout(() => priceEl.classList.remove('cq-flash'), 400);
    }
  }

  const liveEl = document.getElementById('market-live-price');
  if (liveEl && isCurrentMarketContext(activeCtx) && symbol === activeCtx.symbol) {
    const rawPrice = t.price ?? t.lastPrice ?? t.last;
    if (rawPrice != null) {
      liveEl.textContent = '$' + formatTickerPrice(rawPrice);
    }
    const change = t.price_change_percent ?? t.changePercent24h ?? t.changePercent ?? t.priceChangePercent ?? null;
    const liveChange = document.getElementById('market-live-change');
    if (liveChange && change != null) {
      const numChange = Number(change);
      liveChange.textContent = `${numChange >= 0 ? '+' : ''}${numChange.toFixed(2)}%`;
      liveChange.style.color = numChange >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)';
    }
  }
}

/* ── 点击选择交易对 ── */
function selectMarketSymbol(symbol) {
  marketSymbol = symbol;
  invalidateMarketContext();
  // 更新卡片选中态
  document.querySelectorAll('.cq-ticker-card').forEach(c => c.classList.remove('is-active'));
  const active = document.querySelector(`.cq-ticker-card[onclick="selectMarketSymbol('${symbol}')"]`);
  if (active) active.classList.add('is-active');
  // 重新加载K线
  loadMarketKline();
  loadMarketOrderbook();
  // 立即填一次价格
  refreshLivePriceNow();
  // 重连 WS
  startMarketWs();
  startMarketOrderbookPolling(false);
}

/* ── K线周期和交易所切换 ── */
function changeMarketInterval(interval) {
  const supported = new Set(getSupportedMarketIntervals());
  if (supported.size > 0 && !supported.has(interval)) return;
  marketInterval = interval;
  invalidateMarketContext();
  renderMarketIntervalControls();
  loadMarketKline();
  startMarketWs();
}

async function changeMarketExchange(exchange) {
  marketExchange = exchange;
  invalidateMarketContext();
  document.querySelectorAll('.cq-exchange-btn').forEach(b => b.classList.remove('is-active'));
  const active = document.querySelector(`.cq-exchange-btn[data-exchange="${exchange}"]`);
  if (active) active.classList.add('is-active');
  await syncMarketIntervalCapabilities();
  loadMarketKline();
  loadMarketOrderbook();
  refreshLivePriceNow();
  startMarketWs();
  startMarketOrderbookPolling(false);
}

/* 图表类型切换:蜡烛 / 线 — 不重新拉数据,直接复用缓存 */
function changeMarketChartType(type) {
  if (type !== 'candle' && type !== 'line') return;
  marketChartType = type;
  document.querySelectorAll('.cq-chart-type-btn').forEach(b => b.classList.remove('is-active'));
  const active = document.querySelector(`.cq-chart-type-btn[data-chart-type="${type}"]`);
  if (active) active.classList.add('is-active');
  if (marketLastKlines.length > 0) {
    renderKlineChart(marketLastKlines);
  }
}

/* ── K线图加载 ── */
async function loadMarketKline() {
  const ctx = getMarketContext();
  const container = document.getElementById('market-kline-wrap');
  if (!container) return;
  disposeMarketKlineChart();
  container.innerHTML = '<div class="cq-skeleton" style="height:100%;"></div>';

  try {
    const result = await api.getKline(ctx.symbol, ctx.interval, 200, ctx.exchange, ctx.marketType);
    if (!isCurrentMarketContext(ctx)) return;
    const klines = result.klines || [];
    if (klines.length === 0) {
      container.innerHTML = '<div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);"><h3>暂无K线数据</h3></div>';
      marketLastKlines = [];
      return;
    }
    marketLastKlines = klines;
    renderKlineChart(klines);
  } catch (err) {
    if (!isCurrentMarketContext(ctx)) return;
    container.innerHTML = `<div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);"><h3>${escapeHtml(err.message)}</h3></div>`;
    marketLastKlines = [];
  }
}

function formatOrderbookValue(value, digits = 4) {
  const number = Number(value);
  if (!isFinite(number)) return '--';
  if (Math.abs(number) >= 1000) {
    return number.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  if (Math.abs(number) >= 1) return number.toFixed(Math.min(digits, 4));
  return number.toFixed(Math.min(Math.max(digits, 4), 6));
}

function renderMarketOrderbookRows(items, side) {
  if (!Array.isArray(items) || items.length === 0) {
    return '<div class="cq-market-orderbook__empty">暂无盘口数据</div>';
  }

  const maxQuantity = Math.max(...items.map((item) => Number(item.quantity || 0)), 0);
  return items.map((item) => {
    const price = Number(item.price || 0);
    const quantity = Number(item.quantity || 0);
    const depthWidth = maxQuantity > 0 ? Math.max((quantity / maxQuantity) * 100, 4) : 0;
    return `
      <div class="cq-market-orderbook__row cq-market-orderbook__row--${side}">
        <div class="cq-market-orderbook__depth" style="width:${depthWidth.toFixed(1)}%;"></div>
        <span class="cq-market-orderbook__price cq-num">${formatOrderbookValue(price, 2)}</span>
        <span class="cq-market-orderbook__qty cq-num">${formatOrderbookValue(quantity, 4)}</span>
      </div>
    `;
  }).join('');
}

function renderMarketOrderbook(orderbook, ctx = getMarketContext()) {
  const summaryEl = document.getElementById('market-orderbook-summary');
  const bodyEl = document.getElementById('market-orderbook-body');
  const metaEl = document.getElementById('market-orderbook-meta');
  if (!summaryEl || !bodyEl) return;

  const bids = Array.isArray(orderbook?.bids) ? [...orderbook.bids].slice(0, 12) : [];
  const asks = Array.isArray(orderbook?.asks) ? [...orderbook.asks].slice(0, 12) : [];
  const bestBid = Number(bids[0]?.price || 0);
  const bestAsk = Number(asks[0]?.price || 0);
  const spread = bestBid > 0 && bestAsk > 0 ? bestAsk - bestBid : null;
  const spreadPct = spread != null && bestBid > 0 ? (spread / bestBid) * 100 : null;
  const bidTotal = bids.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
  const askTotal = asks.reduce((sum, item) => sum + Number(item.quantity || 0), 0);

  summaryEl.innerHTML = `
    <div class="cq-market-orderbook__metric">
      <span>买一 / 卖一</span>
      <strong class="cq-num">${bestBid ? formatOrderbookValue(bestBid, 2) : '--'} / ${bestAsk ? formatOrderbookValue(bestAsk, 2) : '--'}</strong>
    </div>
    <div class="cq-market-orderbook__metric">
      <span>点差</span>
      <strong class="cq-num">${spread == null ? '--' : formatOrderbookValue(spread, 4)}</strong>
      <em>${spreadPct == null ? '' : `${spreadPct.toFixed(3)}%`}</em>
    </div>
    <div class="cq-market-orderbook__metric">
      <span>深度合计</span>
      <strong class="cq-num">${formatOrderbookValue(bidTotal, 4)} / ${formatOrderbookValue(askTotal, 4)}</strong>
      <em>买 / 卖</em>
    </div>
  `;

  bodyEl.innerHTML = `
    <div class="cq-market-orderbook__section">
      <div class="cq-market-orderbook__section-head">
        <span>卖盘</span>
        <span>价格 / 数量</span>
      </div>
      <div class="cq-market-orderbook__rows">${renderMarketOrderbookRows([...asks].reverse(), 'ask')}</div>
    </div>
    <div class="cq-market-orderbook__spread">
      <span class="cq-tag cq-tag--neutral">${escapeHtml(ctx.exchange.toUpperCase())}</span>
      <span class="cq-tag ${ctx.marketType === 'perp' ? 'cq-tag--warn' : 'cq-tag--info'}">${ctx.marketType === 'perp' ? '永续' : '现货'}</span>
    </div>
    <div class="cq-market-orderbook__section">
      <div class="cq-market-orderbook__section-head">
        <span>买盘</span>
        <span>价格 / 数量</span>
      </div>
      <div class="cq-market-orderbook__rows">${renderMarketOrderbookRows(bids, 'bid')}</div>
    </div>
  `;

  if (metaEl) {
    metaEl.textContent = `订单簿已更新 ${new Date().toLocaleTimeString('zh-CN', { hour12: false })}`;
  }
}

async function loadMarketOrderbook() {
  const ctx = getMarketContext();
  const bodyEl = document.getElementById('market-orderbook-body');
  const summaryEl = document.getElementById('market-orderbook-summary');
  if (!bodyEl || !summaryEl) return;

  bodyEl.innerHTML = '<div class="cq-skeleton" style="height:240px;border-radius:12px;"></div>';
  summaryEl.innerHTML = '';

  try {
    const orderbook = await api.getOrderbook(ctx.symbol, 12, ctx.exchange, ctx.marketType);
    if (!isCurrentMarketContext(ctx)) return;
    renderMarketOrderbook(orderbook, ctx);
  } catch (err) {
    if (!isCurrentMarketContext(ctx)) return;
    bodyEl.innerHTML = `<div class="cq-market-orderbook__empty">${escapeHtml(err.message)}</div>`;
  }
}

function stopMarketOrderbookPolling() {
  if (marketOrderbookTimer) {
    clearInterval(marketOrderbookTimer);
    marketOrderbookTimer = null;
  }
}

function startMarketOrderbookPolling(immediate = true) {
  stopMarketOrderbookPolling();
  if (immediate) {
    loadMarketOrderbook().catch(() => {});
  }
  marketOrderbookTimer = setInterval(() => {
    loadMarketOrderbook().catch(() => {});
  }, MARKET_ORDERBOOK_INTERVAL_MS);
}

/* 把后端返回的 kline 转成 lightweight-charts 数据点
 * 时间统一为 UNIX 秒(整数)。后端可能返回 ms / s / ISO 字符串,做兼容。
 */
function _normalizeKlineTime(raw) {
  if (raw == null) return null;
  if (typeof raw === 'string') {
    const t = Date.parse(raw);
    return isNaN(t) ? null : Math.floor(t / 1000);
  }
  const n = Number(raw);
  if (!isFinite(n)) return null;
  // ms vs s 启发式:13 位以上视为 ms
  return n > 1e11 ? Math.floor(n / 1000) : Math.floor(n);
}

function _marketTimeToDate(time) {
  if (typeof time === 'number') return new Date(time * 1000);
  if (time && typeof time === 'object' && 'year' in time && 'month' in time && 'day' in time) {
    return new Date(Date.UTC(time.year, time.month - 1, time.day));
  }
  return null;
}

function _formatMarketTime(time, options) {
  const date = _marketTimeToDate(time);
  if (!date) return '';
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    ...options,
  }).format(date);
}

function _formatMarketAxisLabel(time) {
  if (['1d', '1w'].includes(marketInterval)) {
    return _formatMarketTime(time, { month: 'numeric', day: 'numeric' });
  }
  return _formatMarketTime(time, { hour: '2-digit', minute: '2-digit', hour12: false });
}

function _formatMarketCrosshairLabel(time) {
  if (['1d', '1w'].includes(marketInterval)) {
    return _formatMarketTime(time, { year: 'numeric', month: 'numeric', day: 'numeric' });
  }
  return _formatMarketTime(time, {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function _toCandleData(klines) {
  const out = [];
  for (const k of klines) {
    // 后端实际字段为 timestamp(ISO 字符串);兼容 openTime/time/数组索引
    const t = _normalizeKlineTime(k.timestamp ?? k.openTime ?? k.time ?? (Array.isArray(k) ? k[0] : null));
    if (t == null) continue;
    out.push({
      time: t,
      open: Number(k.open ?? (Array.isArray(k) ? k[1] : null)),
      high: Number(k.high ?? (Array.isArray(k) ? k[2] : null)),
      low: Number(k.low ?? (Array.isArray(k) ? k[3] : null)),
      close: Number(k.close ?? (Array.isArray(k) ? k[4] : null)),
    });
  }
  // lightweight-charts 要求按时间升序且唯一
  out.sort((a, b) => a.time - b.time);
  const dedup = [];
  for (const p of out) {
    if (dedup.length === 0 || dedup[dedup.length - 1].time !== p.time) dedup.push(p);
  }
  return dedup;
}

function _toLineData(candles) {
  return candles.map(c => ({ time: c.time, value: c.close }));
}

function _buildChartPointFromKline(kline) {
  const time = _normalizeKlineTime(kline.timestamp ?? kline.openTime ?? kline.time);
  if (time == null) return null;
  const open = Number(kline.open);
  const high = Number(kline.high);
  const low = Number(kline.low);
  const close = Number(kline.close);
  if ([open, high, low, close].some(v => !isFinite(v))) return null;
  return { time, open, high, low, close };
}

function _upsertLiveKline(kline) {
  const point = _buildChartPointFromKline(kline);
  if (!point) return null;

  const next = {
    ...kline,
    timestamp: kline.timestamp ?? new Date(point.time * 1000).toISOString(),
  };

  const items = Array.isArray(marketLastKlines) ? [...marketLastKlines] : [];
  const lastIdx = items.length - 1;
  const lastPoint = lastIdx >= 0 ? _buildChartPointFromKline(items[lastIdx]) : null;

  if (lastPoint && lastPoint.time === point.time) {
    items[lastIdx] = { ...items[lastIdx], ...next };
  } else if (!lastPoint || point.time > lastPoint.time) {
    items.push(next);
  } else {
    const idx = items.findIndex(item => {
      const currentPoint = _buildChartPointFromKline(item);
      return currentPoint && currentPoint.time === point.time;
    });
    if (idx >= 0) {
      items[idx] = { ...items[idx], ...next };
    } else {
      items.push(next);
      items.sort((a, b) => (_normalizeKlineTime(a.timestamp) || 0) - (_normalizeKlineTime(b.timestamp) || 0));
    }
  }

  marketLastKlines = items.slice(-200);
  return point;
}

function _updateLiveKlineChart(point) {
  if (!point || !window._klineSeries) return;
  if (marketChartType === 'candle') {
    window._klineSeries.update(point);
    return;
  }
  window._klineSeries.update({ time: point.time, value: point.close });
}

function stopMarketPolling() {
  if (marketPollingTimer) {
    clearInterval(marketPollingTimer);
    marketPollingTimer = null;
  }
}

async function pollMarketSnapshot(ctx = getMarketContext()) {
  const [tickerResult, klineResult] = await Promise.allSettled([
    api.getTicker(ctx.symbol, ctx.exchange, ctx.marketType, true),
    api.getKline(ctx.symbol, ctx.interval, 2, ctx.exchange, ctx.marketType),
  ]);

  if (!isCurrentMarketContext(ctx)) return;

  if (tickerResult.status === 'fulfilled') {
    applyTickerSnapshot(ctx.symbol, tickerResult.value, ctx);
  }

  if (klineResult.status === 'fulfilled') {
    const klines = klineResult.value?.klines || [];
    const latest = klines[klines.length - 1];
    if (latest) {
      const point = _upsertLiveKline(latest);
      _updateLiveKlineChart(point);
      if (latest.close != null) {
        const liveEl = document.getElementById('market-live-price');
        if (liveEl) {
          liveEl.textContent = '$' + formatTickerPrice(latest.close);
        }
        const priceEl = document.getElementById(`ticker-price-${ctx.symbol}`);
        if (priceEl) {
          priceEl.textContent = '$' + formatTickerPrice(latest.close);
        }
      }
      if (tickerResult.status !== 'fulfilled') {
        updateMarketOverviewMeta(new Date());
      }
    }
  }
}

function startMarketPolling(immediate = false) {
  const ctx = getMarketContext();
  if (marketPollingTimer) return;
  if (immediate) {
    pollMarketSnapshot(ctx).catch(() => {});
  }
  marketPollingTimer = setInterval(() => {
    pollMarketSnapshot(ctx).catch(() => {});
  }, MARKET_POLL_INTERVAL_MS);
}

function resetMarketWsWatchdog() {
  if (marketWsWatchdogTimer) {
    clearInterval(marketWsWatchdogTimer);
  }
  marketWsWatchdogTimer = setInterval(() => {
    if (!marketWs || marketWs.readyState !== WebSocket.OPEN) {
      startMarketPolling(true);
      return;
    }
    if (Date.now() - marketWsLastMessageAt >= MARKET_WS_STALE_MS) {
      startMarketPolling(true);
    }
  }, 2000);
}

/* ── 释放图表实例(切换 symbol/interval/页面离开时调用) ── */
function disposeMarketKlineChart() {
  if (window._klineChart && typeof window._klineChart.remove === 'function') {
    try { window._klineChart.remove(); } catch {}
  }
  window._klineChart = null;
  window._klineSeries = null;
  if (window._klineResizeObserver) {
    try { window._klineResizeObserver.disconnect(); } catch {}
    window._klineResizeObserver = null;
  }
}

/* ── K线图渲染(TradingView Lightweight Charts) ── */
function renderKlineChart(klines) {
  const container = document.getElementById('market-kline-wrap');
  if (!container) return;
  if (typeof LightweightCharts === 'undefined') {
    container.innerHTML = '<div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);"><h3>图表库未加载</h3></div>';
    return;
  }

  disposeMarketKlineChart();
  container.innerHTML = '';

  const candles = _toCandleData(klines);
  if (candles.length === 0) {
    container.innerHTML = '<div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);"><h3>暂无K线数据</h3></div>';
    return;
  }

  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  const profit = (getComputedStyle(document.documentElement).getPropertyValue('--cq-color-profit').trim() || '#10B981');
  const loss = (getComputedStyle(document.documentElement).getPropertyValue('--cq-color-loss').trim() || '#EF4444');
  const primary = (getComputedStyle(document.documentElement).getPropertyValue('--cq-color-primary').trim() || '#6366F1');

  const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight,
    layout: {
      background: { type: 'solid', color: 'transparent' },
      textColor: isDark ? '#8B949E' : '#475569',
      fontFamily: "'Geist', 'JetBrains Mono', sans-serif",
      fontSize: 11,
    },
    localization: {
      locale: 'zh-CN',
      timeFormatter: time => _formatMarketCrosshairLabel(time),
    },
    grid: {
      vertLines: { color: isDark ? 'rgba(139,148,158,0.10)' : 'rgba(15,23,42,0.05)' },
      horzLines: { color: isDark ? 'rgba(139,148,158,0.10)' : 'rgba(15,23,42,0.05)' },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: isDark ? 'rgba(139,148,158,0.4)' : 'rgba(15,23,42,0.3)', labelBackgroundColor: primary },
      horzLine: { color: isDark ? 'rgba(139,148,158,0.4)' : 'rgba(15,23,42,0.3)', labelBackgroundColor: primary },
    },
    rightPriceScale: {
      borderColor: isDark ? 'rgba(139,148,158,0.15)' : 'rgba(15,23,42,0.10)',
      scaleMargins: { top: 0.08, bottom: 0.08 },
    },
    timeScale: {
      borderColor: isDark ? 'rgba(139,148,158,0.15)' : 'rgba(15,23,42,0.10)',
      timeVisible: !['1d', '1w'].includes(marketInterval),
      secondsVisible: false,
      tickMarkFormatter: time => _formatMarketAxisLabel(time),
    },
    handleScroll: true,
    handleScale: true,
  });

  let series;
  if (marketChartType === 'candle') {
    series = chart.addCandlestickSeries({
      upColor: profit,
      downColor: loss,
      borderUpColor: profit,
      borderDownColor: loss,
      wickUpColor: profit,
      wickDownColor: loss,
    });
    series.setData(candles);
  } else {
    series = chart.addAreaSeries({
      lineColor: primary,
      lineWidth: 2,
      topColor: isDark ? 'rgba(99,102,241,0.25)' : 'rgba(79,70,229,0.18)',
      bottomColor: 'rgba(99,102,241,0)',
    });
    series.setData(_toLineData(candles));
  }

  chart.timeScale().fitContent();

  // 容器尺寸变化时同步图表宽高
  const ro = new ResizeObserver(entries => {
    for (const e of entries) {
      const { width, height } = e.contentRect;
      chart.applyOptions({ width: Math.floor(width), height: Math.floor(height) });
    }
  });
  ro.observe(container);

  window._klineChart = chart;
  window._klineSeries = series;
  window._klineResizeObserver = ro;
}

/* 主题切换时,如有数据就用新主题色重渲染 */
window.addEventListener('cq:theme-change', () => {
  if (marketLastKlines.length > 0 && document.getElementById('market-kline-wrap')) {
    renderKlineChart(marketLastKlines);
  }
});

/* ── WebSocket 实时推送 ── */
function startMarketWs() {
  const ctx = getMarketContext();
  const sessionId = ++marketWsSessionId;
  stopMarketPolling();
  if (marketWsWatchdogTimer) {
    clearInterval(marketWsWatchdogTimer);
    marketWsWatchdogTimer = null;
  }

  // 清理旧连接（先移除 onclose 防止异步触发重连风暴）
  if (marketWs) {
    marketWs.onclose = null;
    marketWs.onerror = null;
    try { marketWs.close(); } catch {}
    marketWs = null;
  }
  if (marketWsReconnectTimer) {
    clearTimeout(marketWsReconnectTimer);
    marketWsReconnectTimer = null;
  }

  const wsBase = location.protocol === 'https:' ? 'wss:' : 'ws:';
  // WS 端点要求 JWT(在 endpoints.py L18 校验);从 api 客户端取 access token
  const token = (typeof api !== 'undefined' && api.accessToken) || sessionStorage.getItem('access_token') || '';
  if (!token) {
    console.warn('[Market WS] 缺少 access token,跳过 WS 连接(请先登录)');
    startMarketPolling(true);
    return;
  }
  const wsUrl = `${wsBase}//${location.host}/api/v1/ws/market?symbol=${ctx.symbol}&exchange=${ctx.exchange}&market=${ctx.marketType}`;

  const wsProtocols = ['json', `access_token.${token}`];

  try {
    marketWs = new WebSocket(wsUrl, wsProtocols);

    marketWs.onopen = () => {
      if (sessionId !== marketWsSessionId || !isCurrentMarketContext(ctx)) return;
      marketWsLastMessageAt = Date.now();
      resetMarketWsWatchdog();
      console.log('[Market WS] Connected:', ctx.symbol, ctx.exchange);
      // 自动订阅 ticker 频道
      marketWs.send(JSON.stringify({
        action: 'subscribe',
        channels: ['ticker', 'kline'],
        symbols: [ctx.symbol],
        exchange: ctx.exchange,
        market: ctx.marketType,
        interval: ctx.interval,
      }));
    };

    marketWs.onmessage = (event) => {
      try {
        if (sessionId !== marketWsSessionId || !isCurrentMarketContext(ctx)) return;
        const data = JSON.parse(event.data);
        marketWsLastMessageAt = Date.now();
        stopMarketPolling();
        handleMarketWsMessage(data, ctx);
      } catch {}
    };

    marketWs.onclose = () => {
      if (sessionId !== marketWsSessionId || !isCurrentMarketContext(ctx)) return;
      console.log('[Market WS] Disconnected, reconnecting in 5s...');
      startMarketPolling(true);
      marketWsReconnectTimer = setTimeout(() => startMarketWs(), 5000);
    };

    marketWs.onerror = () => {
      marketWs.close();
    };
  } catch (e) {
    console.warn('[Market WS] Failed to connect:', e);
    startMarketPolling(true);
    marketWsReconnectTimer = setTimeout(() => startMarketWs(), 10000);
  }
}

function handleMarketWsMessage(msg, ctx = getMarketContext()) {
  // WSMessage 信封格式: { type, data: { price, ... }, symbol, exchange }
  // 需要从 msg.data 内层读取行情字段
  if (!isCurrentMarketContext(ctx)) return;
  if (msg.type === 'ping') {
    try {
      marketWs?.send(JSON.stringify({ action: 'pong' }));
    } catch {}
    return;
  }

  if (msg.type === 'ticker' && msg.symbol) {
    const t = msg.data || {};  // 内层行情数据
    applyTickerSnapshot(msg.symbol, t, ctx);
    return;
  }

  if (msg.type === 'kline' && msg.symbol === ctx.symbol) {
    const k = msg.data || {};
    const point = _upsertLiveKline(k);
    _updateLiveKlineChart(point);

    const liveEl = document.getElementById('market-live-price');
    if (liveEl && k.close != null) {
      liveEl.textContent = '$' + formatTickerPrice(k.close);
    }
  }
}

/* ── 交易对搜索 ── */
function initMarketSymbolSelector() {
  // 已由 SymbolSelector 处理
  if (!window._marketSymbolSel) {
    const selEl = document.getElementById('market-symbol-selector');
    if (selEl) {
      window._marketSymbolSel = new SymbolSelector({
        containerId: 'market-symbol-selector',
        value: marketSymbol,
        onChange: async (val) => {
          // val 形如 BTCUSDT(现货) 或 BTCUSDT.P(永续) — 拆出 market
          const parsed = (typeof splitMarket === 'function') ? splitMarket(val) : { symbol: val, market: 'spot' };
          marketSymbol = parsed.symbol;
          marketType = parsed.market;
          invalidateMarketContext();
          await syncMarketIntervalCapabilities();
          loadMarketKline();
          loadMarketOrderbook();
          refreshLivePriceNow();
          startMarketWs();
          startMarketOrderbookPolling(false);
        },
      });
    }
  } else if (typeof window._marketSymbolSel.refreshData === 'function') {
    window._marketSymbolSel.refreshData();
  }
}

/* 页面离开时关闭 WS + 释放 K 线图表 */
function stopMarketWs() {
  disposeMarketKlineChart();
  stopMarketPolling();
  stopMarketOrderbookPolling();
  if (marketWs) {
    marketWs.onclose = null;
    marketWs.onerror = null;
    try { marketWs.close(); } catch {}
    marketWs = null;
  }
  if (marketWsReconnectTimer) {
    clearTimeout(marketWsReconnectTimer);
    marketWsReconnectTimer = null;
  }
  if (marketWsWatchdogTimer) {
    clearInterval(marketWsWatchdogTimer);
    marketWsWatchdogTimer = null;
  }
}
