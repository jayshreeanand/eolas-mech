import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from dune_client.client import DuneClient
from dune_client.types import QueryParameter
from dune_client.query import QueryBase
from openai import OpenAI
import os
from dotenv import load_dotenv

DUNE_QUERY_ID = 4861435  # Replace with your actual query ID

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
        self.dune_client = DuneClient.from_env()

    def get_dune_results(self) -> Optional[Dict[str, Any]]:
        """Fetch results from Dune query"""
        try:
            print("Creating Dune query...")
            
            # Create query object
            query = QueryBase(
                name="Grid Pair Analysis",
                query_id=DUNE_QUERY_ID,
                params=[]
            )
            
            print("Fetching results...")
            # Get latest results using the correct method signature
            results = self.dune_client.get_latest_result(DUNE_QUERY_ID)
            
            if not results or not hasattr(results, 'result') or not results.result.rows:
                print("No results returned")
                return None

            print(f"Processing {len(results.result.rows)} rows...")
            return {
                'result': results.result.rows[:100],
                'metadata': {
                    'total_row_count': len(results.result.rows),
                    'returned_row_count': min(len(results.result.rows), 100),
                    'column_names': list(results.result.rows[0].keys()) if results.result.rows else [],
                }
            }
        except Exception as e:
            print(f"Error fetching Dune results: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return None

    def test_connection(self) -> bool:
        """Test the Dune connection with a simple query"""
        try:
            print("Testing Dune connection...")
            # Use a simple public query
            result = self.dune_client.get_latest_result(2030910)
            if result and hasattr(result, 'result'):
                print("Connection successful!")
                print(f"Sample data: {result.result.rows[0] if result.result.rows else 'No rows'}")
                return True
            return False
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False

class GridPairScreener:
    def __init__(self, clients: APIClients, params: GridParameters):
        self.clients = clients
        self.params = params
        self.validate_parameters()
        
    def validate_parameters(self):
        """Validate screening parameters"""
        if self.params.volatility_threshold <= 0:
            raise ValueError("Volatility threshold must be positive")
        if self.params.liquidity_threshold <= 0:
            raise ValueError("Liquidity threshold must be positive")
        if self.params.trend_strength_threshold <= 0:
            raise ValueError("Trend strength threshold must be positive")
        if not (0 < self.params.min_price_range <= self.params.max_price_range):
            raise ValueError("Invalid price range parameters")
        if self.params.grid_levels < 2:
            raise ValueError("Must have at least 2 grid levels")
        if self.params.investment_multiplier <= 0:
            raise ValueError("Investment multiplier must be positive")

    def calculate_volatility(self, price_data: List[Dict]) -> float:
        """Calculate price volatility using standard deviation of returns"""
        try:
            # Extract prices as numpy array
            prices = np.array([float(p['price']) for p in price_data])
            # Calculate log returns
            returns = np.diff(np.log(prices))
            # Calculate annualized volatility
            return np.std(returns) * np.sqrt(len(returns))
        except Exception as e:
            print(f"Error calculating volatility: {e}")
            return 0.0

    def calculate_trend_strength(self, price_data: List[Dict]) -> float:
        """Calculate trend strength using price momentum"""
        try:
            # Extract prices
            prices = np.array([float(p['price']) for p in price_data])
            # Calculate simple moving averages
            short_ma = np.mean(prices[:24])  # 24-hour MA
            long_ma = np.mean(prices)        # Full period MA
            # Calculate trend strength as ratio of MAs
            return abs(short_ma - long_ma) / long_ma
        except Exception as e:
            print(f"Error calculating trend strength: {e}")
            return 0.0

    def parse_price_history(self, values: List[str], timestamps: List[str]) -> List[Dict]:
        """Convert price history arrays into list of price/timestamp dictionaries"""
        try:
            # Clean and parse the values
            clean_values = []
            clean_times = []
            
            for value in values:
                if isinstance(value, str):
                    parts = value.split(',')
                    clean_values.extend([float(v.strip()) for v in parts])
                else:
                    clean_values.append(float(value))
            
            for timestamp in timestamps:
                if isinstance(timestamp, str):
                    parts = timestamp.split(',')
                    clean_times.extend([t.strip() for t in parts])
                else:
                    clean_times.append(str(timestamp))
            
            # Create price history entries
            return [
                {
                    'price': price,
                    'timestamp': ts
                }
                for price, ts in zip(clean_values, clean_times)
            ]
        except Exception as e:
            print(f"Error parsing price history: {e}")
            import traceback
            print(traceback.format_exc())
            return []

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
            print(f"\nAnalyzing {pair_data['pair_name']}...")
            
            # Parse price history
            price_history = self.parse_price_history(
                pair_data['price_history_values'],
                pair_data['price_history_times']
            )
            
            if not price_history:
                print(f"No valid price history for {pair_data['pair_name']}")
                return None
            
            print(f"Calculating metrics for {pair_data['pair_name']}...")
            
            # Calculate metrics
            volatility = self.calculate_volatility(price_history)
            liquidity = float(pair_data['volume_24h'])
            trend_strength = self.calculate_trend_strength(price_history)
            current_price = float(pair_data['current_price'])
            
            print(f"Metrics for {pair_data['pair_name']}:")
            print(f"- Volatility: {volatility:.2%}")
            print(f"- Liquidity: ${liquidity:,.2f}")
            print(f"- Trend Strength: {trend_strength:.2f}")
            
            # Calculate score
            score = (
                (volatility / self.params.volatility_threshold) * 0.4 +
                (liquidity / self.params.liquidity_threshold) * 0.4 +
                (trend_strength / self.params.trend_strength_threshold) * 0.2
            )
            
            # Check if pair meets criteria
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
            else:
                print(f"{pair_data['pair_name']} did not meet criteria")
            
            return None
            
        except Exception as e:
            print(f"Error analyzing pair {pair_data.get('pair_name', 'unknown')}: {e}")
            import traceback
            print(traceback.format_exc())
            return None

    def get_screened_pairs(self) -> List[Dict]:
        """Screen pairs and return those that meet the criteria with recommendations"""
        try:
            results = self.clients.get_dune_results()
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
        
        # Adjust parameters based on actual market conditions
        params = GridParameters(
            volatility_threshold=0.005,   # 0.5% minimum volatility
            liquidity_threshold=50000,    # $50K daily volume
            trend_strength_threshold=0.01, # 1% trend strength
            min_price_range=0.02,         # 2% minimum range
            max_price_range=0.10,         # 10% maximum range
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
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    main()