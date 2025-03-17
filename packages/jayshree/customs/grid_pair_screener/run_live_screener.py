import os
from dotenv import load_dotenv
from grid_pair_screener import GridPairScreener, GridParameters, APIClients

# Dune query to get trading pair data
DUNE_QUERY = """
SELECT 
    CONCAT(token_symbol, '/USDT') as pair_name,
    price as current_price,
    volume_usd as volume_24h,
    -- Get last 30 days of price data
    ARRAY_AGG(
        json_build_object(
            'price', price,
            'timestamp', block_time
        ) ORDER BY block_time DESC
        LIMIT 720 -- 30 days * 24 hours
    ) as price_history
FROM dex.trades
WHERE block_time >= NOW() - INTERVAL '30 days'
    AND token_symbol IN ('BTC', 'ETH', 'SOL', 'AVAX', 'MATIC')
    AND quote_symbol = 'USDT'
GROUP BY 1, 2, 3
ORDER BY volume_usd DESC
LIMIT 10
"""

def setup_live_screener():
    """Initialize the screener with real API connections"""
    # Load environment variables
    load_dotenv()
    
    # Get API keys from environment
    api_keys = {
        "dune": os.getenv("DUNE_API_KEY"),
        "openai": os.getenv("OPENAI_API_KEY")
    }
    
    if not all(api_keys.values()):
        raise ValueError("Missing required API keys in environment variables")
    
    # Initialize API clients
    clients = APIClients(api_keys)
    
    # Set up parameters (these can be adjusted based on your strategy)
    params = GridParameters(
        volatility_threshold=0.02,    # 2% minimum volatility
        liquidity_threshold=1000000,  # $1M daily volume
        trend_strength_threshold=25,   # ADX threshold
        min_price_range=0.05,         # 5% minimum range
        max_price_range=0.20,         # 20% maximum range
        grid_levels=10,               # Number of grid levels
        investment_multiplier=0.001    # 0.1% of daily volume
    )
    
    return GridPairScreener(clients, params)

def main():
    try:
        print("Initializing Grid Pair Screener...")
        screener = setup_live_screener()
        
        print("Fetching and analyzing trading pairs...")
        # You'll need to replace this with your actual Dune query ID
        query_id = 12345  # Replace with your query ID
        
        screened_pairs = screener.get_screened_pairs(query_id)
        
        if not screened_pairs:
            print("\nNo pairs found matching the criteria.")
            return
        
        print("\n=== Grid Pair Screener Results ===\n")
        for idx, pair in enumerate(screened_pairs, 1):
            print(f"\n{idx}. Pair: {pair['pair']}")
            print(f"Score: {pair['analysis']['score']:.2f}")
            
            print("\nAnalysis:")
            print(f"- Volatility: {pair['analysis']['volatility']:.2%}")
            print(f"- Daily Volume: ${pair['analysis']['liquidity']:,.2f}")
            print(f"- Trend Strength: {pair['analysis']['trend_strength']:.2f}")
            
            print("\nGrid Recommendations:")
            print(f"- Range: ${pair['recommendations']['grid_range'][0]:.2f} - "
                  f"${pair['recommendations']['grid_range'][1]:.2f}")
            print(f"- Suggested Investment: ${pair['recommendations']['investment_size']:,.2f}")
            print(f"- Grid Levels: {pair['recommendations']['grid_size']}")
            
            print("\nScenario Analysis:")
            for scenario, details in pair['recommendations']['scenarios'].items():
                print(f"\n{scenario.title()}:")
                print(f"- Potential Profit: {details['potential_profit']:.2f}%")
                print(f"- Expected Trades: {details['grid_trades']}")
            
            print("\n" + "="*50)
            
    except Exception as e:
        print(f"Error running screener: {e}")

if __name__ == "__main__":
    main() 