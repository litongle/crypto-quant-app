'use strict';

function normalizeKlineTime(raw) {
  if (raw == null) return null;
  if (typeof raw === 'number') return raw > 1e11 ? Math.floor(raw / 1000) : Math.floor(raw);
  const parsed = Date.parse(String(raw));
  return Number.isNaN(parsed) ? null : Math.floor(parsed / 1000);
}

function toKlineCandles(klines) {
  const items = [];
  for (const kline of klines || []) {
    const time = normalizeKlineTime(kline.timestamp ?? kline.openTime ?? kline.time ?? (Array.isArray(kline) ? kline[0] : null));
    if (time == null) continue;
    items.push({
      time,
      open: Number(kline.open ?? (Array.isArray(kline) ? kline[1] : null)),
      high: Number(kline.high ?? (Array.isArray(kline) ? kline[2] : null)),
      low: Number(kline.low ?? (Array.isArray(kline) ? kline[3] : null)),
      close: Number(kline.close ?? (Array.isArray(kline) ? kline[4] : null)),
    });
  }
  items.sort((a, b) => a.time - b.time);
  return items.filter((item, index) => index === 0 || items[index - 1].time !== item.time);
}

function destroyKlineChart(containerId) {
  App.state.klineCharts = App.state.klineCharts || {};
  const current = App.state.klineCharts[containerId];
  if (!current) return;
  try { current.ro?.disconnect(); } catch {}
  try { current.chart?.remove(); } catch {}
  delete App.state.klineCharts[containerId];
}

function renderKlineChart(containerId, klines, { chartType = 'candle', height = 320 } = {}) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (typeof LightweightCharts === 'undefined') {
    container.innerHTML = '<div class="cq-empty-inline">图表库未加载</div>';
    return;
  }

  container.style.height = `${height}px`;
  const candles = toKlineCandles(klines);
  destroyKlineChart(containerId);
  container.innerHTML = '';
  if (!candles.length) {
    container.innerHTML = '<div class="cq-empty-inline">暂无 K 线数据</div>';
    return;
  }

  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  const profit = getComputedStyle(document.documentElement).getPropertyValue('--cq-color-profit').trim() || '#10B981';
  const loss = getComputedStyle(document.documentElement).getPropertyValue('--cq-color-loss').trim() || '#EF4444';
  const primary = getComputedStyle(document.documentElement).getPropertyValue('--cq-color-primary').trim() || '#6366F1';

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
    },
    timeScale: {
      borderColor: isDark ? 'rgba(139,148,158,0.15)' : 'rgba(15,23,42,0.10)',
      timeVisible: true,
      secondsVisible: false,
    },
  });

  const series = chartType === 'line'
    ? chart.addAreaSeries({
      lineColor: primary,
      lineWidth: 2,
      topColor: isDark ? 'rgba(99,102,241,0.28)' : 'rgba(79,70,229,0.18)',
      bottomColor: 'rgba(99,102,241,0)',
    })
    : chart.addCandlestickSeries({
      upColor: profit,
      downColor: loss,
      borderUpColor: profit,
      borderDownColor: loss,
      wickUpColor: profit,
      wickDownColor: loss,
    });

  if (chartType === 'line') {
    series.setData(candles.map((item) => ({ time: item.time, value: item.close })));
  } else {
    series.setData(candles);
  }
  chart.timeScale().fitContent();

  const ro = new ResizeObserver((entries) => {
    for (const entry of entries) {
      chart.applyOptions({
        width: Math.floor(entry.contentRect.width),
        height: Math.floor(entry.contentRect.height),
      });
    }
  });
  ro.observe(container);
  App.state.klineCharts = App.state.klineCharts || {};
  App.state.klineCharts[containerId] = { chart, ro, klines, options: { chartType, height } };
}

window.addEventListener('cq:theme-change', () => {
  const charts = App.state.klineCharts || {};
  Object.entries(charts).forEach(([containerId, state]) => {
    if (document.getElementById(containerId)) {
      renderKlineChart(containerId, state.klines, state.options);
    }
  });
});
