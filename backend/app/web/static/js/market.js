/**
 * 行情页面逻辑 v1 — 实时价格 + K线 + WebSocket
 */

/* 默认关注的交易对 */
const DEFAULT_WATCHLIST = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'DOGEUSDT'];

/* 当前选中的交易对和K线周期 */
let marketSymbol = 'BTCUSDT';
let marketInterval = '1h';
let marketExchange = 'binance';
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
    return;
  }

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

/* ── 点击选择交易对 ── */
function selectMarketSymbol(symbol) {
  marketSymbol = symbol;
  // 更新卡片选中态
  document.querySelectorAll('.cq-ticker-card').forEach(c => c.classList.remove('is-active'));
  const active = document.querySelector(`.cq-ticker-card[onclick="selectMarketSymbol('${symbol}')"]`);
  if (active) active.classList.add('is-active');
  // 重新加载K线
  loadMarketKline();
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
  startMarketWs();
}

/* ── K线图加载 ── */
async function loadMarketKline() {
  const container = document.getElementById('market-kline-wrap');
  if (!container) return;
  container.innerHTML = '<div class="cq-skeleton" style="height:300px;"></div>';

  try {
    const result = await api.getKline(marketSymbol, marketInterval, 200, marketExchange);
    const klines = result.klines || [];
    if (klines.length === 0) {
      container.innerHTML = '<div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);"><h3>暂无K线数据</h3></div>';
      return;
    }
    renderKlineChart(klines);
  } catch (err) {
    container.innerHTML = `<div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);"><h3>${escapeHtml(err.message)}</h3></div>`;
  }
}

/* ── K线图渲染（使用 Chart.js 蜡烛图模拟） ── */
function renderKlineChart(klines) {
  const container = document.getElementById('market-kline-wrap');
  container.innerHTML = '<div style="position:relative;height:320px;width:100%;"><canvas id="marketKlineChart"></canvas></div>';

  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  const gridColor = isDark ? 'rgba(139,148,158,0.12)' : 'rgba(15,23,42,0.06)';
  const tickColor = isDark ? '#6E7681' : '#94A3B8';
  const primaryColor = getComputedStyle(document.documentElement).getPropertyValue('--cq-color-primary').trim() || '#6366F1';

  const labels = [];
  const closes = [];
  const highs = [];
  const lows = [];

  klines.forEach(k => {
    const time = k.openTime || k.time || k[0];
    const close = k.close ?? k[4];
    const high = k.high ?? k[2];
    const low = k.low ?? k[3];
    labels.push(formatKlineTime(time));
    closes.push(Number(close));
    highs.push(Number(high));
    lows.push(Number(low));
  });

  if (window._klineChart) window._klineChart.destroy();

  const canvas = document.getElementById('marketKlineChart');
  const ctx = canvas.getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 280);
  gradient.addColorStop(0, isDark ? 'rgba(99,102,241,0.10)' : 'rgba(79,70,229,0.06)');
  gradient.addColorStop(1, 'rgba(99,102,241,0)');

  window._klineChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '收盘价',
          data: closes,
          borderColor: primaryColor,
          backgroundColor: gradient,
          borderWidth: 1.5,
          fill: true,
          tension: 0.1,
          pointRadius: 0,
          pointHoverRadius: 3,
        },
        {
          label: '最高',
          data: highs,
          borderColor: 'rgba(16,185,129,0.3)',
          borderWidth: 0.5,
          borderDash: [2, 2],
          fill: false,
          pointRadius: 0,
        },
        {
          label: '最低',
          data: lows,
          borderColor: 'rgba(239,68,68,0.3)',
          borderWidth: 0.5,
          borderDash: [2, 2],
          fill: false,
          pointRadius: 0,
        },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: isDark ? '#1C2333' : '#FFFFFF',
          titleColor: isDark ? '#E6EDF3' : '#0F172A',
          bodyColor: isDark ? '#8B949E' : '#475569',
          borderColor: isDark ? 'rgba(139,148,158,0.12)' : 'rgba(15,23,42,0.08)',
          borderWidth: 1,
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: $${Number(ctx.raw).toLocaleString('en-US', { maximumFractionDigits: 2 })}`
          }
        }
      },
      scales: {
        x: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10, family: "'Geist', sans-serif" }, maxTicksLimit: 10 } },
        y: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10, family: "'JetBrains Mono', monospace" }, callback: formatAxisValue } }
      }
    }
  });
}

function formatKlineTime(ts) {
  if (!ts) return '';
  const d = new Date(typeof ts === 'number' ? ts : ts);
  if (isNaN(d.getTime())) return '';
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const h = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  if (['1d', '1w'].includes(marketInterval)) return `${m}-${day}`;
  return `${m}-${day} ${h}:${min}`;
}

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
  const wsUrl = `${wsBase}//${location.host}/api/v1/ws/market?symbol=${marketSymbol}&exchange=${marketExchange}&token=${encodeURIComponent(token)}`;

  try {
    marketWs = new WebSocket(wsUrl);

    marketWs.onopen = () => {
      console.log('[Market WS] Connected:', marketSymbol, marketExchange);
      // 自动订阅 ticker 频道
      marketWs.send(JSON.stringify({
        action: 'subscribe',
        channels: ['ticker'],
        symbols: [marketSymbol],
        exchange: marketExchange,
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
          marketSymbol = val;
          loadMarketKline();
          startMarketWs();
        },
      });
    }
  }
}

/* 页面离开时关闭 WS */
function stopMarketWs() {
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
