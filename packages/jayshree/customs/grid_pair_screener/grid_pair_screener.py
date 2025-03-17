import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from dune_client.client import DuneClient
from openai import OpenAI

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

    def get_dune_results(self, query_id: int) -> Optional[Dict[str, Any]]:
        """Fetch the latest results from a Dune query"""
        try:
            result = self.dune_client.get_latest_result(query_id)
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
            current_price = float(pair_data['price_history'][-1]['price'])
            
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

    def get_screened_pairs(self, query_id: int) -> List[Dict]:
        """Screen pairs and return those that meet the criteria with recommendations"""
        try:
            results = self.clients.get_dune_results(query_id)
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