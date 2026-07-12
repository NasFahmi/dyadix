import os
import sys
import json
import argparse
import webbrowser
import logging
import pandas as pd
from datetime import datetime
from typing import Dict

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from service.market.hyperliquid.hyperliquid_service import HyperliquidService
from features.liquidity.liquidity import LiquidityEngine
from features.technical.order_block import OrderBlockEngine

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dyadix — Market Intelligence Visualization</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lightweight-charts@4.2.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        :root {
            --bg-color: #0b0d10;
            --panel-bg: rgba(18, 22, 28, 0.75);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --accent-bullish: #10b981;
            --accent-bearish: #f43f5e;
            --accent-purple: #8b5cf6;
            --accent-gold: #f59e0b;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            overflow: hidden;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 24px;
            background-color: rgba(11, 13, 16, 0.9);
            border-bottom: 1px solid var(--border-color);
            backdrop-filter: blur(12px);
            z-index: 10;
        }

        .logo-section {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo {
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 1px;
            background: linear-gradient(135deg, #a78bfa, #8b5cf6, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .badge {
            background-color: rgba(139, 92, 246, 0.15);
            color: #c084fc;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            border: 1px solid rgba(139, 92, 246, 0.3);
        }

        .market-meta {
            display: flex;
            gap: 24px;
        }

        .meta-item {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
        }

        .meta-label {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-secondary);
        }

        .meta-value {
            font-size: 14px;
            font-weight: 700;
        }

        .main-container {
            display: flex;
            flex: 1;
            overflow: hidden;
        }

        .chart-section {
            flex: 1;
            position: relative;
            background-color: #08090b;
        }

        #chart-container {
            width: 100%;
            height: 100%;
        }

        .sidebar {
            width: 380px;
            background-color: var(--panel-bg);
            border-left: 1px solid var(--border-color);
            backdrop-filter: blur(16px);
            display: flex;
            flex-direction: column;
            overflow-y: auto;
            padding: 24px;
            gap: 20px;
        }

        .card {
            background-color: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .card-title {
            font-size: 11px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.75px;
            color: var(--text-secondary);
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 8px;
        }

        .sentiment-badge {
            font-size: 20px;
            font-weight: 800;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .sentiment-Bullish { color: var(--accent-bullish); }
        .sentiment-Bearish { color: var(--accent-bearish); }
        .sentiment-Neutral { color: var(--accent-gold); }

        .desc-text {
            font-size: 13px;
            line-height: 1.6;
            color: var(--text-secondary);
        }

        .list-items {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .list-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            padding: 6px 0;
            border-bottom: 1px dashed rgba(255, 255, 255, 0.03);
        }

        .list-item:last-child {
            border-bottom: none;
        }

        .label-pill {
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
        }

        .pill-bullish {
            background-color: rgba(16, 185, 129, 0.15);
            color: var(--accent-bullish);
        }

        .pill-bearish {
            background-color: rgba(244, 63, 94, 0.15);
            color: var(--accent-bearish);
        }

        .pill-neutral {
            background-color: rgba(245, 158, 11, 0.15);
            color: var(--accent-gold);
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-section">
            <span class="logo">DYADIX</span>
            <span class="badge">CHART ENGINE</span>
        </div>
        <div class="market-meta">
            <div class="meta-item">
                <span class="meta-label">Symbol</span>
                <span class="meta-value" id="meta-symbol">BTCUSDC</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Timeframe</span>
                <span class="meta-value" id="meta-timeframe">15m</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Last Price</span>
                <span class="meta-value" id="meta-price" style="color: var(--accent-bullish)">$0.00</span>
            </div>
        </div>
    </header>

    <div class="main-container">
        <div class="chart-section">
            <div id="chart-container"></div>
        </div>
        <div class="sidebar">
            <!-- Sentiment Card -->
            <div class="card">
                <span class="card-title">Liquidity Sentiment</span>
                <div class="sentiment-badge" id="sentiment-val">Neutral</div>
            </div>

            <!-- Interpretation Card -->
            <div class="card">
                <span class="card-title">Interpretation</span>
                <div class="desc-text" id="interpretation-text">Analyzing market liquidity and SMC zones...</div>
            </div>

            <!-- Sweeps Card -->
            <div class="card">
                <span class="card-title">Recent Sweeps</span>
                <div class="list-items" id="sweeps-list">
                    <div class="desc-text">No recent sweeps detected.</div>
                </div>
            </div>

            <!-- Active Order Blocks -->
            <div class="card">
                <span class="card-title">Active Order Blocks</span>
                <div class="list-items" id="obs-list">
                    <div class="desc-text">No active order blocks in range.</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const chartData = $DATA_JSON;

        // Update Headers
        document.getElementById('meta-symbol').textContent = chartData.symbol;
        document.getElementById('meta-timeframe').textContent = chartData.timeframe;
        document.getElementById('meta-price').textContent = '$' + chartData.current_price.toLocaleString();
        
        const sentimentVal = document.getElementById('sentiment-val');
        sentimentVal.textContent = chartData.sentiment;
        sentimentVal.className = 'sentiment-badge sentiment-' + chartData.sentiment;

        document.getElementById('interpretation-text').textContent = chartData.interpretation;

        // Render Recent Sweeps
        const sweepsList = document.getElementById('sweeps-list');
        if (chartData.sweeps && chartData.sweeps.length > 0) {
            sweepsList.innerHTML = '';
            chartData.sweeps.forEach(s => {
                const isBull = s.type.includes('Bullish');
                const badgeClass = isBull ? 'pill-bullish' : 'pill-bearish';
                sweepsList.innerHTML += `
                    <div class="list-item">
                        <span><b>${s.level}</b> Sweep</span>
                        <span class="label-pill ${badgeClass}">${s.type} @ $${s.level_price.toLocaleString()}</span>
                    </div>
                `;
            });
        }

        // Render Active Order Blocks
        const obsList = document.getElementById('obs-list');
        if ((chartData.bullish_obs && chartData.bullish_obs.length > 0) || (chartData.bearish_obs && chartData.bearish_obs.length > 0)) {
            obsList.innerHTML = '';
            chartData.bullish_obs.forEach(ob => {
                obsList.innerHTML += `
                    <div class="list-item">
                        <span>Bullish OB</span>
                        <span class="label-pill pill-bullish">$${ob.bottom.toLocaleString()} - $${ob.top.toLocaleString()}</span>
                    </div>
                `;
            });
            chartData.bearish_obs.forEach(ob => {
                obsList.innerHTML += `
                    <div class="list-item">
                        <span>Bearish OB</span>
                        <span class="label-pill pill-bearish">$${ob.bottom.toLocaleString()} - $${ob.top.toLocaleString()}</span>
                    </div>
                `;
            });
        }

        // Create TradingView Chart
        const chart = LightweightCharts.createChart(document.getElementById('chart-container'), {
            layout: {
                background: { type: LightweightCharts.ColorType.Solid, color: '#08090b' },
                textColor: '#9ca3af',
                fontSize: 11,
                fontFamily: 'Plus Jakarta Sans',
            },
            grid: {
                vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
                horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: 'rgba(255, 255, 255, 0.08)',
            },
            timeScale: {
                borderColor: 'rgba(255, 255, 255, 0.08)',
                timeVisible: true,
                secondsVisible: false,
            },
        });

        // Add Candlestick Series
        const candleSeries = chart.addCandlestickSeries({
            upColor: '#10b981',
            downColor: '#f43f5e',
            borderVisible: false,
            wickUpColor: '#10b981',
            wickDownColor: '#f43f5e',
        });

        candleSeries.setData(chartData.candles);

        // Add Liquidity Lines
        if (chartData.liquidity_pools.highs) {
            chartData.liquidity_pools.highs.forEach(pool => {
                const color = '#f43f5e';
                const style = pool.strength === 'Strong' ? LightweightCharts.LineStyle.Solid : LightweightCharts.LineStyle.Dashed;
                candleSeries.createPriceLine({
                    price: pool.price,
                    color: color,
                    lineWidth: pool.strength === 'Strong' ? 2 : 1,
                    lineStyle: style,
                    axisLabelVisible: true,
                    title: `High Pool (${pool.strength}) [Touches: ${pool.touches}]`,
                });
            });
        }

        if (chartData.liquidity_pools.lows) {
            chartData.liquidity_pools.lows.forEach(pool => {
                const color = '#10b981';
                const style = pool.strength === 'Strong' ? LightweightCharts.LineStyle.Solid : LightweightCharts.LineStyle.Dashed;
                candleSeries.createPriceLine({
                    price: pool.price,
                    color: color,
                    lineWidth: pool.strength === 'Strong' ? 2 : 1,
                    lineStyle: style,
                    axisLabelVisible: true,
                    title: `Low Pool (${pool.strength}) [Touches: ${pool.touches}]`,
                });
            });
        }

        // Add PDH / PDL Lines
        if (chartData.key_levels.pdh) {
            candleSeries.createPriceLine({
                price: chartData.key_levels.pdh,
                color: '#8b5cf6',
                lineWidth: 1.5,
                lineStyle: LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: 'Previous Day High (PDH)',
            });
        }
        if (chartData.key_levels.pdl) {
            candleSeries.createPriceLine({
                price: chartData.key_levels.pdl,
                color: '#8b5cf6',
                lineWidth: 1.5,
                lineStyle: LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: 'Previous Day Low (PDL)',
            });
        }

        // Add Order Block Lines
        chartData.bullish_obs.forEach(ob => {
            candleSeries.createPriceLine({
                price: ob.top,
                color: 'rgba(16, 185, 129, 0.4)',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'Bullish OB Top',
            });
            candleSeries.createPriceLine({
                price: ob.bottom,
                color: 'rgba(16, 185, 129, 0.4)',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'Bullish OB Bottom',
            });
        });

        chartData.bearish_obs.forEach(ob => {
            candleSeries.createPriceLine({
                price: ob.top,
                color: 'rgba(244, 63, 94, 0.4)',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'Bearish OB Top',
            });
            candleSeries.createPriceLine({
                price: ob.bottom,
                color: 'rgba(244, 63, 94, 0.4)',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'Bearish OB Bottom',
            });
        });

        // Add Markers (OB Creation & Sweeps)
        const markers = [];
        
        chartData.bullish_obs.forEach(ob => {
            markers.push({
                time: ob.created_time,
                position: 'belowBar',
                color: '#10b981',
                shape: 'arrowUp',
                text: 'Bullish OB Formed'
            });
        });

        chartData.bearish_obs.forEach(ob => {
            markers.push({
                time: ob.created_time,
                position: 'aboveBar',
                color: '#f43f5e',
                shape: 'arrowDown',
                text: 'Bearish OB Formed'
            });
        });

        // Add Sweeps markers
        if (chartData.sweeps_with_time) {
            chartData.sweeps_with_time.forEach(sw => {
                markers.push({
                    time: sw.time,
                    position: sw.type.includes('Bullish') ? 'belowBar' : 'aboveBar',
                    color: '#f59e0b',
                    shape: 'circle',
                    text: `SWEEP ${sw.level}`
                });
            });
        }

        // Sort markers by time
        markers.sort((a, b) => a.time - b.time);
        
        // Remove duplicate markers on the same candle to look cleaner
        const uniqueMarkers = [];
        const seenTimes = new Set();
        markers.forEach(m => {
            if (!seenTimes.has(m.time)) {
                seenTimes.add(m.time);
                uniqueMarkers.push(m);
            }
        });

        candleSeries.setMarkers(uniqueMarkers);

        // Auto-fit chart columns
        chart.timeScale().fitContent();

        // Responsive resize
        window.addEventListener('resize', () => {
            chart.resize(document.getElementById('chart-container').offsetWidth, document.getElementById('chart-container').offsetHeight);
        });
    </script>
</body>
</html>
"""

def get_daily_bias_mock(df_hl: pd.DataFrame) -> Dict:
    """Mock or calculate daily high/low for PDH/PDL sweeps using last 24h data."""
    if df_hl.empty:
        return {}
    try:
        pdl = df_hl["low"].min()
        pdh = df_hl["high"].max()
        return {"previous_day_high": pdh, "previous_day_low": pdl}
    except Exception:
        return {}

def main():
    parser = argparse.ArgumentParser(description="Dyadix Market Analysis Visualizer")
    parser.add_argument("--pair", type=str, default="BTCUSDC", help="Symbol to analyze (e.g., BTCUSDC)")
    parser.add_argument("--timeframe", type=str, default="15m", help="Timeframe (e.g., 3m, 5m, 15m, 1h)")
    parser.add_argument("--limit", type=int, default=300, help="Number of candles (default 300)")
    args = parser.parse_args()

    logger.info(f"Starting visualization for {args.pair} ({args.timeframe}) with limit={args.limit}...")
    
    # 1. Initialize Service & Fetch Data
    service = HyperliquidService()
    df = service.fetch_ohlcv(symbol=args.pair, timeframe=args.timeframe, limit=args.limit)
    
    if df.empty or len(df) < 50:
        logger.error(f"Failed to fetch sufficient candles for {args.pair}. Require at least 50 candles.")
        sys.exit(1)

    # 2. Get Daily Bias (for PDH/PDL calculations)
    df_daily = service.fetch_ohlcv(symbol=args.pair, timeframe="1d", limit=2)
    daily_bias = {}
    if not df_daily.empty:
        prev_day = df_daily.iloc[-2] if len(df_daily) >= 2 else df_daily.iloc[-1]
        daily_bias = {
            "previous_day_high": float(prev_day["high"]),
            "previous_day_low": float(prev_day["low"])
        }

    # 3. Calculate Liquidity Pools & Sweeps
    logger.info("Calculating Liquidity pools and sweeps...")
    liq_results = LiquidityEngine.calculate(df, daily_bias=daily_bias, timeframe=args.timeframe)
    
    # 4. Calculate Order Blocks
    logger.info("Calculating unmitigated Order Blocks...")
    active_bullish, active_bearish = OrderBlockEngine.get_active_obs(df)

    # 5. Format Data for Lightweight Charts
    candles_list = []
    for idx, row in df.iterrows():
        unix_sec = int(idx.timestamp())
        candles_list.append({
            "time": unix_sec,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        })

    # Format Order Blocks with creation times
    bullish_obs_formatted = []
    for ob in active_bullish:
        idx_ob = ob["index"]
        created_time = int(df.index[idx_ob].timestamp())
        bullish_obs_formatted.append({
            "top": float(ob["top"]),
            "bottom": float(ob["bottom"]),
            "created_time": created_time
        })

    bearish_obs_formatted = []
    for ob in active_bearish:
        idx_ob = ob["index"]
        created_time = int(df.index[idx_ob].timestamp())
        bearish_obs_formatted.append({
            "top": float(ob["top"]),
            "bottom": float(ob["bottom"]),
            "created_time": created_time
        })

    # Find the exact timestamp of sweeps (since sweeps are within the last 8 candles)
    sweeps_with_time = []
    for sweep in liq_results.get("recent_sweeps", []):
        level_price = sweep["level_price"]
        sweep_type = sweep["type"]
        target_time = None
        for i in range(-1, -9, -1):
            try:
                candle_row = df.iloc[i]
                candle_time = int(df.index[i].timestamp())
                if "Bearish" in sweep_type and candle_row["high"] >= level_price:
                    target_time = candle_time
                    break
                elif "Bullish" in sweep_type and candle_row["low"] <= level_price:
                    target_time = candle_time
                    break
            except IndexError:
                break
        
        if not target_time:
            target_time = int(df.index[-1].timestamp())
            
        sweeps_with_time.append({
            "time": target_time,
            "level": sweep["level"],
            "type": sweep_type,
            "level_price": level_price
        })

    # 6. Build Final Data JSON
    final_data = {
        "symbol": args.pair,
        "timeframe": args.timeframe,
        "current_price": float(df["close"].iloc[-1]),
        "sentiment": liq_results.get("liquidity_sentiment", "Neutral"),
        "interpretation": liq_results.get("interpretation", ""),
        "key_levels": liq_results.get("key_levels", {}),
        "liquidity_pools": liq_results.get("liquidity_pools", {"highs": [], "lows": []}),
        "sweeps": liq_results.get("recent_sweeps", []),
        "sweeps_with_time": sweeps_with_time,
        "bullish_obs": bullish_obs_formatted,
        "bearish_obs": bearish_obs_formatted,
        "candles": candles_list
    }

    # Write HTML file
    output_html_content = HTML_TEMPLATE.replace("$DATA_JSON", json.dumps(final_data))
    output_file_name = "market_chart.html"
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "result")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_file_name)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_html_content)
        
    logger.info(f"Successfully generated visualizer dashboard: {output_path}")
    
    # Try opening it in a web browser
    try:
        webbrowser.open(f"file:///{output_path}")
        logger.info("Automatically opened visualization in web browser.")
    except Exception as e:
        logger.warning(f"Could not automatically open web browser: {e}. You can open '{output_file_name}' manually.")

if __name__ == "__main__":
    main()
