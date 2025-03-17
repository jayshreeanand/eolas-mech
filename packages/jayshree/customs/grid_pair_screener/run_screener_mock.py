from grid_pair_screener import GridPairScreener, GridParameters, APIClients
from unittest.mock import Mock, MagicMock
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any

class MockAPIClients:
    def __init__(self, api_keys: Dict[str, str]):
        self.dune_client = MagicMock()
        self.openai_client = MagicMock()
    
    def get_dune_results(self, query_id: int) -> Dict[str, Any]:
        # Return mock data
        return {
            'result': create_mock_pair_data(),
            'metadata': {
                'total_row_count': 5,
                'returned_row_count': 5,
                'column_names': ['pair_name', 'price_history', 'volume_24h', 'current_price']
            }
        }

def generate_mock_price_data(base_price=100, days=30, volatility=0.02):
    """Generate mock price history data"""
    prices = []
    current_price = base_price
    
    for i in range(days * 24):  # Hourly data for n days
        current_price *= np.exp(np.random.normal(0, volatility))
        prices.append({
            'price': str(current_price),
            'timestamp': (datetime.now() - timedelta(hours=i)).isoformat()
        })
    
    return list(reversed(prices))

def create_mock_pair_data():
    """Create mock trading pair data"""
    pairs = [
        ("BTC/USDT", 30000, 5000000000),
        ("ETH/USDT", 2000, 2000000000),
        ("SOL/USDT", 100, 500000000),
        ("AVAX/USDT", 50, 100000000),
        ("MATIC/USDT", 1, 50000000)
    ]
    
    return [
        {
            'pair_name': pair_name,
            'price_history': generate_mock_price_data(base_price, 30),
            'volume_24h': str(volume),
            'current_price': str(base_price)
        }
        for pair_name, base_price, volume in pairs
    ]

def main():
    # Create mock clients
    mock_clients = MockAPIClients({
        "dune": "mock_dune_key",
        "openai": "mock_openai_key"
    })
    
    # Set up parameters
    params = GridParameters(
        volatility_threshold=0.02,
        liquidity_threshold=1000000,
        trend_strength_threshold=25,
        min_price_range=0.05,
        max_price_range=0.20,
        grid_levels=10,
        investment_multiplier=0.001
    )
    
    # Initialize screener with mock clients
    screener = GridPairScreener(mock_clients, params)
    
    try:
        # Get screened pairs
        screened_pairs = screener.get_screened_pairs(12345)  # Query ID doesn't matter for mock
        
        # Print results
        print("\n=== Grid Pair Screener Results (Mock Data) ===\n")
        
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