from grid_pair_screener import GridPairScreener, GridParameters, APIClients
import os
from dotenv import load_dotenv

def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize API keys
    api_keys = {
        "dune": os.getenv("DUNE_API_KEY"),
        "openai": os.getenv("OPENAI_API_KEY")
    }
    
    # Initialize API clients
    clients = APIClients(api_keys)
    
    # Set up parameters (you can adjust these values)
    params = GridParameters(
        volatility_threshold=0.02,    # 2% minimum volatility
        liquidity_threshold=1000000,  # $1M daily volume
        trend_strength_threshold=25,   # ADX threshold
        min_price_range=0.05,         # 5% minimum range
        max_price_range=0.20,         # 20% maximum range
        grid_levels=10,               # Number of grid levels
        investment_multiplier=0.001    # 0.1% of daily volume
    )
    
    # Initialize screener
    screener = GridPairScreener(clients, params)
    
    # Example Dune query ID that returns cryptocurrency pair data
    # Replace this with your actual query ID
    query_id = 12345  # Your Dune query ID here
    
    try:
        # Get screened pairs
        screened_pairs = screener.get_screened_pairs(query_id)
        
        # Print results
        print("\n=== Grid Pair Screener Results ===\n")
        
        if not screened_pairs:
            print("No pairs found matching the criteria.")
            return
            
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