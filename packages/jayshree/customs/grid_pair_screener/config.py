# Trading pair configuration
TRADING_PAIRS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "AVAX/USDT",
    "MATIC/USDT"
]

# Screening parameters
SCREENING_PARAMS = {
    "volatility_threshold": 0.02,
    "liquidity_threshold": 1000000,
    "trend_strength_threshold": 25,
    "min_price_range": 0.05,
    "max_price_range": 0.20,
    "grid_levels": 10,
    "investment_multiplier": 0.001
}

# Dune query configuration
DUNE_QUERY_ID = 12345  # Replace with your query ID 