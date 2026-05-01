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

async function loadMarketPage() {
  // 渲染头部行情概览卡片
  try {
    const tickers = await api.getBatchTickers();
    renderMarketOverview(tickers);
  } catch {
    renderMarketOverview([]);
  }

  // 加载K线图
  await loadMarketKline();

  // 立即拉一次实时价格,避免首次进页面卡在 "-- --"
  refreshLivePriceNow();

  // 启动 WebSocket
  startMarketWs();

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
  const liveEl = document.getElementById('market-live-price');
  const liveChange = document.getElementById('market-live-change');
  if (!liveEl) return;
  try {
    const t = await api.getTicker(marketSymbol, marketExchange, marketType);
    const rawPrice = t.price ?? t.lastPrice ?? t.last;
    if (rawPrice != null) liveEl.textContent = '$' + formatTickerPrice(rawPrice);
    const change = t.price_change_percent ?? t.changePercent24h ?? t.changePercent ?? t.priceChangePercent ?? null;
    if (liveChange && change != null) {
      const numChange = Number(change);
      liveChange.textContent = `${numChange >= 0 ? '+' : ''}${numChange.toFixed(2)}%`;
      liveChange.style.color = numChange >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)';
    }
  } catch (e) {
    // 拿不到就让 WS 兜底,什么都不做
  }
}

/* ── 点击选择交易对 ── */
function selectMarketSymbol(symbol) {
  marketSymbol = symbol;
  // 更新卡片选中态
  document.querySelectorAll('.cq-ticker-card').forEach(c => c.classList.remove('is-active'));
  const active = document.querySelector(`.cq-ticker-card[onclick="selectMarketSymbol('${symbol}')"]`);
  if (active) active.classList.add('is-active');
  // 重新加载K线
  loadMarketKline();
  // 立即填一次价格
  refreshLivePriceNow();
  // 重连 WS
  startMarketWs();
}

/* ── K线周期和交易所切换 ── */
function changeMarketInterval(interval) {
  marketInterval = interval;
  document.querySelectorAll('.cq-interval-btn').forEach(b => b.classList.remove('is-active'));
  const active = document.querySelector(`.cq-interval-btn[data-interval="${interval}"]`);
  if (active) active.classList.add('is-active');
  loadMarketKline();
}

function changeMarketExchange(exchange) {
  marketExchange = exchange;
  document.querySelectorAll('.cq-exchange-btn').forEach(b => b.classList.remove('is-active'));
  const active = document.querySelector(`.cq-exchange-btn[data-exchange="${exchange}"]`);
  if (active) active.classList.add('is-active');
  loadMarketKline();
  refreshLivePriceNow();
  startMarketWs();
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
  const container = document.getElementById('market-kline-wrap');
  if (!container) return;
  disposeMarketKlineChart();
  container.innerHTML = '<div class="cq-skeleton" style="height:100%;"></div>';

  try {
    const result = await api.getKline(marketSymbol, marketInterval, 200, marketExchange, marketType);
    const klines = result.klines || [];
    if (klines.length === 0) {
      container.innerHTML = '<div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);"><h3>暂无K线数据</h3></div>';
      marketLastKlines = [];
      return;
    }
    marketLastKlines = klines;
    renderKlineChart(klines);
  } catch (err) {
    container.innerHTML = `<div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);"><h3>${escapeHtml(err.message)}</h3></div>`;
    marketLastKlines = [];
  }
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
  const token = (typeof api !== 'undefined' && api.accessToken) || localStorage.getItem('access_token') || '';
  if (!token) {
    console.warn('[Market WS] 缺少 access token,跳过 WS 连接(请先登录)');
    return;
  }
  const wsUrl = `${wsBase}//${location.host}/api/v1/ws/market?symbol=${marketSymbol}&exchange=${marketExchange}&market=${marketType}`;

  try {
    marketWs = new WebSocket(wsUrl);

    marketWs.onopen = () => {
      console.log('[Market WS] Connected:', marketSymbol, marketExchange);
      // 先发送认证消息（Token 不再走 URL）
      marketWs.send(JSON.stringify({
        action: 'auth',
        token: token,
      }));
      // 自动订阅 ticker 频道
      marketWs.send(JSON.stringify({
        action: 'subscribe',
        channels: ['ticker'],
        symbols: [marketSymbol],
        exchange: marketExchange,
        market: marketType,
      }));
    };

    marketWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleMarketWsMessage(data);
      } catch {}
    };

    marketWs.onclose = () => {
      console.log('[Market WS] Disconnected, reconnecting in 5s...');
      marketWsReconnectTimer = setTimeout(() => startMarketWs(), 5000);
    };

    marketWs.onerror = () => {
      marketWs.close();
    };
  } catch (e) {
    console.warn('[Market WS] Failed to connect:', e);
    marketWsReconnectTimer = setTimeout(() => startMarketWs(), 10000);
  }
}

function handleMarketWsMessage(msg) {
  // WSMessage 信封格式: { type, data: { price, ... }, symbol, exchange }
  // 需要从 msg.data 内层读取行情字段
  if (msg.type === 'ticker' && msg.symbol) {
    const t = msg.data || {};  // 内层行情数据
    updateMarketOverviewMeta(new Date());

    // 更新价格卡片
    const priceEl = document.getElementById(`ticker-price-${msg.symbol}`);
    if (priceEl) {
      const rawPrice = t.price || t.lastPrice || t.last;
      const newPrice = formatTickerPrice(rawPrice);
      priceEl.textContent = '$' + newPrice;
      // 闪烁效果
      priceEl.classList.add('cq-flash');
      setTimeout(() => priceEl.classList.remove('cq-flash'), 400);
    }

    // 更新实时价格显示
    const liveEl = document.getElementById('market-live-price');
    if (liveEl && msg.symbol === marketSymbol) {
      const rawPrice = t.price || t.lastPrice || t.last;
      liveEl.textContent = '$' + formatTickerPrice(rawPrice);
      // 读取涨跌幅: 兼容多种字段名 (snake_case / camelCase)
      const change = t.price_change_percent ?? t.changePercent24h ?? t.changePercent ?? t.priceChangePercent ?? 0;
      const liveChange = document.getElementById('market-live-change');
      if (liveChange) {
        const numChange = Number(change);
        liveChange.textContent = `${numChange >= 0 ? '+' : ''}${numChange.toFixed(2)}%`;
        liveChange.style.color = numChange >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)';
      }
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
        onChange: (val) => {
          // val 形如 BTCUSDT(现货) 或 BTCUSDT.P(永续) — 拆出 market
          const parsed = (typeof splitMarket === 'function') ? splitMarket(val) : { symbol: val, market: 'spot' };
          marketSymbol = parsed.symbol;
          marketType = parsed.market;
          loadMarketKline();
          refreshLivePriceNow();
          startMarketWs();
        },
      });
    }
  }
}

/* 页面离开时关闭 WS + 释放 K 线图表 */
function stopMarketWs() {
  disposeMarketKlineChart();
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
}
