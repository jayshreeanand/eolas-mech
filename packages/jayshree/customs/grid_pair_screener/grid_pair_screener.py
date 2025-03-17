import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

@dataclass
class GridParameters:
    volatility_threshold: float  # Minimum volatility required
    liquidity_threshold: float   # Minimum daily volume in USD
    trend_strength_threshold: float  # ADX threshold
    min_price_range: float  # Minimum price range for grid
    max_price_range: float  # Maximum price range for grid
    grid_levels: int  # Number of grid levels
    investment_multiplier: float  # Multiplier for investment size based on volume

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
        # Simplified ADX calculation
        prices = pd.DataFrame([float(p['price']) for p in price_data])
        return prices.rolling(window=14).std().iloc[-1]

    def suggest_grid_setup(self, pair_analysis: PairAnalysis) -> Dict:
        """Suggest grid setup based on pair analysis"""
        price = pair_analysis.current_price
        volatility = pair_analysis.volatility
        
        # Calculate grid range based on volatility
        range_percentage = min(volatility * 2, self.params.max_price_range)
        upper_price = price * (1 + range_percentage)
        lower_price = price * (1 - range_percentage)
        
        # Calculate grid size based on volatility and range
        grid_size = max(
            self.params.grid_levels,
            int((upper_price - lower_price) / (price * 0.01))
        )
        
        # Calculate suggested investment based on liquidity
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
            current_price = float(pair_data['price_history'][-1]['price'])
            
            # Score the pair based on parameters
            score = (
                (volatility / self.params.volatility_threshold) * 0.4 +
                (liquidity / self.params.liquidity_threshold) * 0.4 +
                (trend_strength / self.params.trend_strength_threshold) * 0.2
            )
            
            # Check if pair meets minimum criteria
            if (volatility >= self.params.volatility_threshold and
                liquidity >= self.params.liquidity_threshold and
                trend_strength >= self.params.trend_strength_threshold):
                
                # Calculate suggested grid range
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

    def get_screened_pairs(self, query_id: int) -> List[Dict]:
        """Screen pairs and return those that meet the criteria with recommendations"""
        try:
            # Fetch market data from Dune
            results = get_dune_results(self.clients, query_id)
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
            
            # Sort by score
            return sorted(screened_pairs, key=lambda x: x['analysis']['score'], reverse=True)
            
        except Exception as e:
            print(f"Error screening pairs: {e}")
            return []

# Update the run function to include pair screening
@with_key_rotation
def run(
    prompt: str,
    api_keys: Any,
    **kwargs: Any,
) -> Tuple[str, Optional[str], Optional[Dict[str, Any]], Any]:
    try:
        clients = APIClients(api_keys)
        
        # Default parameters (can be customized)
        params = GridParameters(
            volatility_threshold=0.02,  # 2% daily volatility minimum
            liquidity_threshold=1000000,  # $1M daily volume minimum
            trend_strength_threshold=25,  # ADX threshold
            min_price_range=0.05,  # 5% minimum range
            max_price_range=0.20,  # 20% maximum range
            grid_levels=10,  # Default grid levels
            investment_multiplier=0.001  # 0.1% of daily volume
        )
        
        screener = GridPairScreener(clients, params)
        query_id, question = extract_query_details(prompt)
        
        if not query_id:
            return "Could not determine Dune query ID. Please provide a valid query ID.", "", None, None
            
        screened_pairs = screener.get_screened_pairs(query_id)
        
        if not screened_pairs:
            return "No pairs meeting the criteria were found.", "", None, None
            
        # Format response
        response = "Top Grid Trading Pairs:\n\n"
        for pair in screened_pairs[:5]:  # Show top 5 pairs
            response += f"Pair: {pair['pair']}\n"
            response += f"Score: {pair['analysis']['score']:.2f}\n"
            response += f"Grid Range: {pair['recommendations']['grid_range'][0]:.2f} - {pair['recommendations']['grid_range'][1]:.2f}\n"
            response += f"Suggested Investment: ${pair['recommendations']['investment_size']:,.2f}\n"
            response += f"Grid Levels: {pair['recommendations']['grid_size']}\n"
            response += "\nScenario Analysis:\n"
            for scenario, details in pair['recommendations']['scenarios'].items():
                response += f"- {scenario.title()}: {details['potential_profit']:.2f}% potential profit with {details['grid_trades']} trades\n"
            response += "\n"
            
        metadata_dict = {
            "screened_pairs": screened_pairs,
            "parameters": vars(params),
            "timestamp": datetime.now().isoformat()
        }
        
        return response, "", metadata_dict, None
        
    except Exception as e:
        return str(e), "", None, None