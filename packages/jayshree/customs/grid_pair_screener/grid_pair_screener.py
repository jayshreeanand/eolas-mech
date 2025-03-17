import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from dune_client.client import DuneClient
from openai import OpenAI
import os
from dotenv import load_dotenv

# Configuration
DUNE_QUERY = """
SELECT 
    CONCAT(token_symbol, '/USDT') as pair_name,
    price as current_price,
    volume_usd as volume_24h,
    ARRAY_AGG(
        json_build_object(
            'price', price,
            'timestamp', block_time
        ) ORDER BY block_time DESC
        LIMIT 720
    ) as price_history
FROM dex.trades
WHERE block_time >= NOW() - INTERVAL '30 days'
    AND token_symbol IN ('BTC', 'ETH', 'SOL', 'AVAX', 'MATIC')
    AND quote_symbol = 'USDT'
GROUP BY 1, 2, 3
ORDER BY volume_usd DESC
LIMIT 10
"""

@dataclass
class GridParameters:
    volatility_threshold: float
    liquidity_threshold: float
    trend_strength_threshold: float
    min_price_range: float
    max_price_range: float
    grid_levels: int
    investment_multiplier: float

@dataclass
class PairAnalysis:
    pair_name: str
    volatility: float
    liquidity: float
    trend_strength: float
    current_price: float
    suggested_grid_range: Tuple[float, float]
    suggested_investment: float
    suggested_grid_size: int
    score: float

class APIClients:
    def __init__(self, api_keys: Dict[str, str]):
        self.dune_api_key = api_keys["dune"]
        self.openai_api_key = api_keys["openai"]
        
        if not all([self.dune_api_key, self.openai_api_key]):
            raise ValueError("Missing required API keys")
            
        self.openai_client = OpenAI(api_key=self.openai_api_key)
        self.dune_client = DuneClient(self.dune_api_key)

    def get_dune_results(self, query_text: str) -> Optional[Dict[str, Any]]:
        """Execute Dune query and fetch results"""
        try:
            # Create and execute query
            query = self.dune_client.execute(
                query=query_text,
                name="Grid Pair Analysis"
            )
            
            # Wait for and fetch results
            result = self.dune_client.get_result(query)
            
            return {
                'result': result.result.rows[:100],
                'metadata': {
                    'total_row_count': len(result.result.rows),
                    'returned_row_count': min(len(result.result.rows), 100),
                    'column_names': list(result.result.rows[0].keys()) if result.result.rows else [],
                }
            }
        except Exception as e:
            print(f"Error fetching Dune results: {e}")
            return None

class GridPairScreener:
    def __init__(self, clients: APIClients, params: GridParameters):
        self.clients = clients
        self.params = params
        
    def calculate_volatility(self, price_data: List[Dict]) -> float:
        """Calculate price volatility using standard deviation of returns"""
        prices = [float(p['price']) for p in price_data]
        returns = np.diff(np.log(prices))
        return np.std(returns) * np.sqrt(len(returns))

    def calculate_trend_strength(self, price_data: List[Dict]) -> float:
        """Calculate ADX for trend strength"""
        prices = pd.DataFrame([float(p['price']) for p in price_data])
        return prices.rolling(window=14).std().iloc[-1]

    def suggest_grid_setup(self, pair_analysis: PairAnalysis) -> Dict:
        """Suggest grid setup based on pair analysis"""
        price = pair_analysis.current_price
        volatility = pair_analysis.volatility
        
        range_percentage = min(volatility * 2, self.params.max_price_range)
        upper_price = price * (1 + range_percentage)
        lower_price = price * (1 - range_percentage)
        
        grid_size = max(
            self.params.grid_levels,
            int((upper_price - lower_price) / (price * 0.01))
        )
        
        suggested_investment = pair_analysis.liquidity * self.params.investment_multiplier
        
        return {
            "grid_range": (lower_price, upper_price),
            "grid_size": grid_size,
            "investment_size": suggested_investment,
            "scenarios": self.generate_scenarios(price, lower_price, upper_price, grid_size)
        }

    def generate_scenarios(
        self, 
        current_price: float, 
        lower_price: float, 
        upper_price: float, 
        grid_size: int
    ) -> Dict:
        """Generate potential scenarios for the grid setup"""
        grid_interval = (upper_price - lower_price) / grid_size
        
        return {
            "uptrend": {
                "scenario": "Price moves from current to upper range",
                "potential_profit": ((upper_price - current_price) / current_price) * 100,
                "grid_trades": int((upper_price - current_price) / grid_interval)
            },
            "downtrend": {
                "scenario": "Price moves from current to lower range",
                "potential_profit": ((current_price - lower_price) / current_price) * 100,
                "grid_trades": int((current_price - lower_price) / grid_interval)
            },
            "sideways": {
                "scenario": "Price oscillates within 25% of the range",
                "potential_profit": (grid_interval / current_price) * 100 * (grid_size // 4),
                "grid_trades": grid_size // 2
            }
        }

    def analyze_pair(self, pair_data: Dict) -> Optional[PairAnalysis]:
        """Analyze a trading pair and return analysis if it meets criteria"""
        try:
            volatility = self.calculate_volatility(pair_data['price_history'])
            liquidity = float(pair_data['volume_24h'])
            trend_strength = self.calculate_trend_strength(pair_data['price_history'])
            current_price = float(pair_data['current_price'])
            
            score = (
                (volatility / self.params.volatility_threshold) * 0.4 +
                (liquidity / self.params.liquidity_threshold) * 0.4 +
                (trend_strength / self.params.trend_strength_threshold) * 0.2
            )
            
            if (volatility >= self.params.volatility_threshold and
                liquidity >= self.params.liquidity_threshold and
                trend_strength >= self.params.trend_strength_threshold):
                
                range_percentage = min(volatility * 2, self.params.max_price_range)
                grid_range = (
                    current_price * (1 - range_percentage),
                    current_price * (1 + range_percentage)
                )
                
                return PairAnalysis(
                    pair_name=pair_data['pair_name'],
                    volatility=volatility,
                    liquidity=liquidity,
                    trend_strength=trend_strength,
                    current_price=current_price,
                    suggested_grid_range=grid_range,
                    suggested_investment=liquidity * self.params.investment_multiplier,
                    suggested_grid_size=self.params.grid_levels,
                    score=score
                )
            
            return None
            
        except Exception as e:
            print(f"Error analyzing pair: {e}")
            return None

    def get_screened_pairs(self) -> List[Dict]:
        """Screen pairs and return those that meet the criteria with recommendations"""
        try:
            results = self.clients.get_dune_results(DUNE_QUERY)
            if not results:
                return []
            
            screened_pairs = []
            for pair_data in results['result']:
                analysis = self.analyze_pair(pair_data)
                if analysis:
                    grid_setup = self.suggest_grid_setup(analysis)
                    screened_pairs.append({
                        "pair": analysis.pair_name,
                        "analysis": {
                            "volatility": analysis.volatility,
                            "liquidity": analysis.liquidity,
                            "trend_strength": analysis.trend_strength,
                            "score": analysis.score
                        },
                        "recommendations": grid_setup
                    })
            
            return sorted(screened_pairs, key=lambda x: x['analysis']['score'], reverse=True)
            
        except Exception as e:
            print(f"Error screening pairs: {e}")
            return []

def main():
    try:
        # Load environment variables
        load_dotenv()
        
        # Get API keys from environment
        api_keys = {
            "dune": os.getenv("DUNE_API_KEY"),
            "openai": os.getenv("OPENAI_API_KEY")
        }
        
        if not all(api_keys.values()):
            raise ValueError("Missing required API keys in environment variables")
        
        # Set up parameters
        params = GridParameters(
            volatility_threshold=0.02,    # 2% minimum volatility
            liquidity_threshold=1000000,  # $1M daily volume
            trend_strength_threshold=25,   # ADX threshold
            min_price_range=0.05,         # 5% minimum range
            max_price_range=0.20,         # 20% maximum range
            grid_levels=10,               # Number of grid levels
            investment_multiplier=0.001    # 0.1% of daily volume
        )
        
        print("Initializing Grid Pair Screener...")
        clients = APIClients(api_keys)
        screener = GridPairScreener(clients, params)
        
        print("Fetching and analyzing trading pairs...")
        screened_pairs = screener.get_screened_pairs()
        
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