#!/usr/bin/env python
"""
Development server launcher for RSI Layered Extreme Value Tracking Trading System
This script provides a simplified development environment with mock data
"""

import os
import sys
import json
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("dev-server")

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
    from typing import Dict, List, Optional
    import random
    from datetime import datetime, timedelta
    import json
    from dotenv import load_dotenv
except ImportError:
    logger.error("Required packages not found. Install with: pip install fastapi uvicorn python-dotenv")
    sys.exit(1)

# Load environment variables from .env file
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="RSI Layered Extreme Value Tracking Trading System",
    description="A quantitative trading system for cryptocurrency markets",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Mock Data Models ---

class Position(BaseModel):
    id: str
    symbol: str
    direction: str
    entryPrice: float
    currentPrice: float
    amount: float
    leverage: int
    margin: float
    unrealizedPnl: float
    unrealizedPnlPercentage: float
    stopLoss: Optional[float] = None
    takeProfit: Optional[float] = None
    liquidationPrice: float
    riskLevel: str
    createdAt: datetime
    updatedAt: datetime
    accountId: str
    accountName: str
    strategyId: Optional[str] = None
    strategyName: Optional[str] = None
    fundingRate: Optional[float] = None
    fundingFee: Optional[float] = None
    priceChange: float = 0

class Order(BaseModel):
    id: str
    orderId: str
    clientOrderId: str
    symbol: str
    side: str
    type: str
    price: Optional[float] = None
    amount: float
    filled: float
    status: str
    createdAt: datetime
    updatedAt: datetime
    accountId: str
    accountName: str
    source: str
    leverage: int
    margin: float
    fee: float
    triggerPrice: Optional[float] = None
    trailingDistance: Optional[float] = None
    timeInForce: Optional[str] = None
    postOnly: bool = False
    reduceOnly: bool = False
    avgFillPrice: Optional[float] = None

class Trade(BaseModel):
    id: str
    symbol: str
    direction: str
    entryPrice: float
    exitPrice: float
    amount: float
    leverage: int
    realizedPnl: float
    realizedPnlPercentage: float
    margin: float
    openTime: datetime
    closeTime: datetime
    holdingTime: str
    closeReason: str
    accountId: str
    accountName: str
    strategyId: Optional[str] = None
    strategyName: Optional[str] = None
    fundingRate: Optional[float] = None
    fundingFee: Optional[float] = None
    fee: Optional[float] = None

class Strategy(BaseModel):
    id: str
    name: str
    type: str
    symbol: str
    status: str
    enabled: bool
    totalTrades: int
    winRate: float
    totalPnl: float
    returnRate: float
    sharpeRatio: float
    maxDrawdown: float
    profitLossRatio: float
    createdAt: datetime
    updatedAt: datetime
    creator: str
    description: Optional[str] = None
    parameters: Dict[str, Any] = {}
    tags: List[str] = []
    isTemplate: bool = False
    initialCapital: float = 10000.0
    
# --- Mock Data Generator ---

def generate_mock_positions(count: int = 10) -> List[Position]:
    positions = []
    symbols = ["ETH-USDT", "BTC-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"]
    directions = ["long", "short"]
    risk_levels = ["low", "medium", "high"]
    account_names = ["OKX主账户", "OKX子账户1", "OKX子账户2", "Binance账户"]
    strategy_names = ["RSI分层策略", "MACD策略", "布林带策略", None]
    
    for i in range(count):
        symbol = random.choice(symbols)
        direction = random.choice(directions)
        entry_price = round(random.uniform(100, 50000), 2)
        price_change = round(random.uniform(-5, 5), 2)
        current_price = round(entry_price * (1 + price_change/100), 2)
        amount = round(random.uniform(0.1, 10), 4)
        leverage = random.randint(1, 100)
        margin = round(amount * entry_price / leverage, 2)
        unrealized_pnl = round((current_price - entry_price) * amount * (1 if direction == "long" else -1), 2)
        unrealized_pnl_percentage = round(unrealized_pnl / margin * 100, 2)
        
        liquidation_price = round(
            entry_price * (1 - 0.9/leverage) if direction == "long" else entry_price * (1 + 0.9/leverage),
            2
        )
        
        strategy_id = f"strategy_{random.randint(1, 5)}" if random.random() > 0.3 else None
        strategy_name = random.choice(strategy_names)
        
        created_days_ago = random.randint(1, 30)
        created_at = datetime.now() - timedelta(days=created_days_ago)
        updated_at = created_at + timedelta(hours=random.randint(1, 24*created_days_ago))
        
        positions.append(Position(
            id=f"pos_{i+1}",
            symbol=symbol,
            direction=direction,
            entryPrice=entry_price,
            currentPrice=current_price,
            amount=amount,
            leverage=leverage,
            margin=margin,
            unrealizedPnl=unrealized_pnl,
            unrealizedPnlPercentage=unrealized_pnl_percentage,
            stopLoss=round(entry_price * 0.95, 2) if random.random() > 0.5 else None,
            takeProfit=round(entry_price * 1.05, 2) if random.random() > 0.5 else None,
            liquidationPrice=liquidation_price,
            riskLevel=random.choice(risk_levels),
            createdAt=created_at,
            updatedAt=updated_at,
            accountId=f"account_{random.randint(1, 4)}",
            accountName=random.choice(account_names),
            strategyId=strategy_id,
            strategyName=strategy_name,
            fundingRate=round(random.uniform(-0.01, 0.01), 4),
            fundingFee=round(random.uniform(-10, 10), 2),
            priceChange=price_change
        ))
    
    return positions

def generate_mock_orders(count: int = 20) -> List[Order]:
    orders = []
    symbols = ["ETH-USDT", "BTC-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"]
    sides = ["buy", "sell"]
    types = ["market", "limit", "stop", "trailing_stop"]
    statuses = ["pending", "open", "filled", "partially_filled", "cancelled", "rejected", "expired"]
    sources = ["manual", "strategy", "api", "tp_sl"]
    account_names = ["OKX主账户", "OKX子账户1", "OKX子账户2", "Binance账户"]
    
    for i in range(count):
        symbol = random.choice(symbols)
        side = random.choice(sides)
        order_type = random.choice(types)
        status = random.choice(statuses)
        
        price = round(random.uniform(100, 50000), 2) if order_type != "market" else None
        amount = round(random.uniform(0.1, 10), 4)
        filled = round(amount * random.uniform(0, 1), 4) if status in ["partially_filled", "filled"] else 0
        if status == "filled":
            filled = amount
            
        created_days_ago = random.randint(0, 7)
        created_at = datetime.now() - timedelta(days=created_days_ago)

        # Ensure the upper bound of randint is at least 1 to avoid ValueError
        max_minutes = 60 * 24 * created_days_ago  # total minutes since creation day
        if max_minutes == 0:
            max_minutes = 60  # default to within the first hour when created today

        updated_at = created_at + timedelta(minutes=random.randint(1, max_minutes))
        
        leverage = random.randint(1, 100)
        margin = round(amount * (price or 1000) / leverage, 2)
        fee = round(filled * (price or 1000) * 0.0005, 4)
        
        orders.append(Order(
            id=f"order_{i+1}",
            orderId=f"ord_{random.randint(100000, 999999)}",
            clientOrderId=f"cli_{random.randint(100000, 999999)}",
            symbol=symbol,
            side=side,
            type=order_type,
            price=price,
            amount=amount,
            filled=filled,
            status=status,
            createdAt=created_at,
            updatedAt=updated_at,
            accountId=f"account_{random.randint(1, 4)}",
            accountName=random.choice(account_names),
            source=random.choice(sources),
            leverage=leverage,
            margin=margin,
            fee=fee,
            triggerPrice=round(random.uniform(100, 50000), 2) if order_type in ["stop", "stop_limit"] else None,
            trailingDistance=round(random.uniform(10, 100), 2) if order_type == "trailing_stop" else None,
            timeInForce=random.choice(["GTC", "IOC", "FOK"]),
            postOnly=random.choice([True, False]),
            reduceOnly=random.choice([True, False]),
            avgFillPrice=round(random.uniform(100, 50000), 2) if filled > 0 else None
        ))
    
    return orders

def generate_mock_trades(count: int = 30) -> List[Trade]:
    trades = []
    symbols = ["ETH-USDT", "BTC-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"]
    directions = ["long", "short"]
    close_reasons = ["manual", "take_profit", "stop_loss", "liquidation", "strategy", "system"]
    account_names = ["OKX主账户", "OKX子账户1", "OKX子账户2", "Binance账户"]
    strategy_names = ["RSI分层策略", "MACD策略", "布林带策略", None]
    
    for i in range(count):
        symbol = random.choice(symbols)
        direction = random.choice(directions)
        entry_price = round(random.uniform(100, 50000), 2)
        exit_price = round(entry_price * (1 + random.uniform(-0.2, 0.2)), 2)
        amount = round(random.uniform(0.1, 10), 4)
        leverage = random.randint(1, 100)
        margin = round(amount * entry_price / leverage, 2)
        
        realized_pnl = round((exit_price - entry_price) * amount * (1 if direction == "long" else -1), 2)
        realized_pnl_percentage = round(realized_pnl / margin * 100, 2)
        
        days_ago = random.randint(1, 90)
        hours_held = random.randint(1, 24*7)
        
        open_time = datetime.now() - timedelta(days=days_ago)
        close_time = open_time + timedelta(hours=hours_held)
        
        holding_time = f"{hours_held}小时" if hours_held < 24 else f"{hours_held//24}天{hours_held%24}小时"
        
        strategy_id = f"strategy_{random.randint(1, 5)}" if random.random() > 0.3 else None
        strategy_name = random.choice(strategy_names)
        
        trades.append(Trade(
            id=f"trade_{i+1}",
            symbol=symbol,
            direction=direction,
            entryPrice=entry_price,
            exitPrice=exit_price,
            amount=amount,
            leverage=leverage,
            realizedPnl=realized_pnl,
            realizedPnlPercentage=realized_pnl_percentage,
            margin=margin,
            openTime=open_time,
            closeTime=close_time,
            holdingTime=holding_time,
            closeReason=random.choice(close_reasons),
            accountId=f"account_{random.randint(1, 4)}",
            accountName=random.choice(account_names),
            strategyId=strategy_id,
            strategyName=strategy_name,
            fundingRate=round(random.uniform(-0.01, 0.01), 4),
            fundingFee=round(random.uniform(-10, 10), 2),
            fee=round(amount * exit_price * 0.0005, 4)
        ))
    
    return trades

def generate_mock_strategies(count: int = 15) -> List[Strategy]:
    strategies = []
    types = ["rsi_layered", "macd", "bollinger", "dual_ma", "grid", "custom"]
    symbols = ["ETH-USDT", "BTC-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"]
    statuses = ["running", "paused", "stopped", "error"]
    creators = ["system", "admin", "user1", "user2"]
    tags = ["趋势跟踪", "震荡策略", "高频", "低频", "套利", "稳健", "激进"]
    
    for i in range(count):
        strategy_type = random.choice(types)
        
        # Generate appropriate parameters based on strategy type
        parameters = {}
        if strategy_type == "rsi_layered":
            parameters = {
                "rsi_period": random.randint(7, 21),
                "long_level1": random.randint(30, 40),
                "long_level2": random.randint(20, 30),
                "long_level3": random.randint(10, 20),
                "short_level1": random.randint(60, 70),
                "short_level2": random.randint(70, 80),
                "short_level3": random.randint(80, 90),
                "retracement_points": random.randint(1, 5)
            }
        elif strategy_type == "macd":
            parameters = {
                "fast_length": random.randint(8, 16),
                "slow_length": random.randint(20, 30),
                "signal_length": random.randint(5, 10)
            }
        elif strategy_type == "bollinger":
            parameters = {
                "length": random.randint(10, 30),
                "std_dev": random.uniform(1.5, 3.0),
                "mean_type": random.choice(["sma", "ema", "wma"])
            }
        
        total_trades = random.randint(10, 500)
        win_count = random.randint(0, total_trades)
        win_rate = round(win_count / total_trades * 100, 2) if total_trades > 0 else 0
        
        total_pnl = round(random.uniform(-5000, 20000), 2)
        return_rate = round(total_pnl / 10000 * 100, 2)
        
        created_days_ago = random.randint(10, 365)
        created_at = datetime.now() - timedelta(days=created_days_ago)
        updated_at = created_at + timedelta(days=random.randint(1, created_days_ago))
        
        # Generate random tags
        strategy_tags = random.sample(tags, random.randint(1, 3)) if random.random() > 0.3 else []
        
        strategies.append(Strategy(
            id=f"strategy_{i+1}",
            name=f"{random.choice(['RSI', 'MACD', 'BB', 'MA', 'Grid'])} {random.choice(['Alpha', 'Beta', 'Gamma', 'Delta'])} {random.randint(1, 9)}",
            type=strategy_type,
            symbol=random.choice(symbols),
            status=random.choice(statuses),
            enabled=random.choice([True, False]),
            totalTrades=total_trades,
            winRate=win_rate,
            totalPnl=total_pnl,
            returnRate=return_rate,
            sharpeRatio=round(random.uniform(-1, 3), 2),
            maxDrawdown=round(random.uniform(5, 50), 2),
            profitLossRatio=round(random.uniform(0.5, 3), 2),
            createdAt=created_at,
            updatedAt=updated_at,
            creator=random.choice(creators),
            description=f"这是一个{random.choice(['高频', '中频', '低频'])}交易策略，适合{random.choice(['震荡', '趋势', '盘整'])}行情。" if random.random() > 0.3 else None,
            parameters=parameters,
            tags=strategy_tags,
            isTemplate=random.random() < 0.2,
            initialCapital=10000.0
        ))
    
    return strategies

# Generate initial mock data
mock_positions = generate_mock_positions(15)
mock_orders = generate_mock_orders(25)
mock_trades = generate_mock_trades(40)
mock_strategies = generate_mock_strategies(20)

# --- API Routes ---

@app.get("/api/v1/trading/positions", tags=["Trading"])
async def get_positions():
    """Get all active positions"""
    return {
        "success": True,
        "positions": mock_positions,
        "total": len(mock_positions)
    }

@app.get("/api/v1/trading/orders", tags=["Trading"])
async def get_orders():
    """Get all active orders"""
    active_orders = [order for order in mock_orders if order.status in ["pending", "open", "partially_filled"]]
    return {
        "success": True,
        "orders": active_orders,
        "total": len(active_orders)
    }

@app.get("/api/v1/trading/history", tags=["Trading"])
async def get_trading_history(
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all")
):
    """Get trading history"""
    days = 30
    if time_range == "7d":
        days = 7
    elif time_range == "90d":
        days = 90
    elif time_range == "all":
        days = 365
    
    cutoff_date = datetime.now() - timedelta(days=days)
    filtered_trades = [trade for trade in mock_trades if trade.closeTime >= cutoff_date]
    
    return {
        "success": True,
        "trades": filtered_trades,
        "total": len(filtered_trades)
    }

@app.get("/api/v1/strategy", tags=["Strategy"])
async def get_strategies():
    """Get all strategies"""
    return {
        "success": True,
        "strategies": mock_strategies,
        "total": len(mock_strategies)
    }

@app.get("/api/v1/strategy/templates", tags=["Strategy"])
async def get_strategy_templates():
    """Get strategy templates"""
    templates = [s for s in mock_strategies if s.isTemplate]
    return {
        "success": True,
        "templates": templates,
        "total": len(templates)
    }

@app.get("/api/v1/system/status", tags=["System"])
async def get_system_status():
    """Get system status"""
    return {
        "success": True,
        "status": "running",
        "version": "0.1.0",
        "uptime": "3d 12h 45m",
        "cpu_usage": random.uniform(5, 80),
        "memory_usage": random.uniform(20, 90),
        "disk_usage": random.uniform(30, 70),
        "active_strategies": len([s for s in mock_strategies if s.status == "running"]),
        "active_positions": len(mock_positions),
        "active_orders": len([o for o in mock_orders if o.status in ["pending", "open", "partially_filled"]]),
        "last_backup": (datetime.now() - timedelta(hours=random.randint(1, 24))).isoformat(),
        "database_size": f"{random.uniform(10, 500):.2f} MB"
    }

# --- WebSocket Support ---

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Simulate receiving message from client
            data = await websocket.receive_text()
            request = json.loads(data)
            
            # Handle different subscription types
            if request.get("type") == "subscribe":
                topic = request.get("topic", "")
                
                if topic == "ticker":
                    # Send ticker data every 2 seconds
                    for _ in range(5):  # Just send 5 updates for demo
                        ticker_data = {
                            "type": "ticker",
                            "data": {
                                "symbol": "ETH-USDT",
                                "price": round(random.uniform(2000, 3000), 2),
                                "change": round(random.uniform(-5, 5), 2),
                                "volume": round(random.uniform(10000, 100000), 2),
                                "timestamp": datetime.now().isoformat()
                            }
                        }
                        await websocket.send_text(json.dumps(ticker_data))
                        await asyncio.sleep(2)
                
                elif topic == "positions":
                    # Send position updates
                    for pos in mock_positions[:3]:  # Just send a few positions
                        pos_data = {
                            "type": "position_update",
                            "data": json.loads(pos.json())
                        }
                        await websocket.send_text(json.dumps(pos_data))
                        await asyncio.sleep(1)
            
            # Echo the received message
            await websocket.send_text(f"Message received: {data}")
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# --- Main Entry Point ---

def start_dev_server():
    """Start the development server"""
    port = int(os.getenv("WEB_PORT", "8080"))
    host = os.getenv("WEB_HOST", "0.0.0.0")
    
    logger.info(f"Starting development server at http://{host}:{port}")
    logger.info(f"API documentation available at http://{host}:{port}/api/docs")
    logger.info("Press Ctrl+C to stop the server")
    
    # Check if frontend directory exists
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
    if os.path.exists(frontend_dir) and os.path.isdir(frontend_dir):
        logger.info(f"Serving frontend from {frontend_dir}")
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    
    # Start the server
    uvicorn.run(
        "run_dev:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    # Import asyncio here to avoid import error when imported as a module
    import asyncio
    start_dev_server()
