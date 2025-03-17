A **Grid Trading Pair Screener** is a tool that helps traders identify the best trading pairs for **grid trading** based on predefined criteria like **volatility, liquidity, and trend patterns**. It continuously monitors market conditions and suggests the optimal grid parameters for automated trading.

## **How It Works**

1. **Data Collection**

   - Fetches real-time trading data from Dune Analytics
   - Analyzes price history, volume, and market metrics

2. **Pair Analysis**

   - Calculates volatility using standard deviation of returns
   - Assesses liquidity through 24-hour trading volume
   - Measures trend strength using price momentum

3. **Grid Setup**

   - Determines optimal grid ranges based on volatility
   - Suggests investment size based on liquidity
   - Calculates potential profit scenarios

4. **Screening Process**
   - Filters pairs based on minimum criteria
   - Ranks pairs by composite score
   - Generates detailed recommendations

### **Why Use It?**

- **Automates Pair Selection** → No need to manually check charts.
- **Optimized Grid Settings** → Maximizes efficiency and profitability.
- **Real-time Adjustments** → Adapts to changing market conditions.

## **Dune Query**

The screener uses the following Dune query to fetch market data:

```WITH recent_trades AS (
    SELECT
        token_bought_symbol as token_symbol,
        block_time,
        amount_usd,
        token_bought_amount
    FROM dex.trades
    WHERE block_time >= NOW() - interval '30' day
    AND token_bought_symbol IN ('WBTC', 'ETH', 'WMATIC', 'AVAX', 'SOL')
    AND amount_usd > 0
    AND token_bought_amount > 0
),
price_data AS (
    SELECT
        token_symbol,
        block_time,
        amount_usd / token_bought_amount as price,
        amount_usd as volume
    FROM recent_trades
    WHERE token_bought_amount > 0
),
hourly_data AS (
    SELECT
        token_symbol,
        date_trunc('hour', block_time) as hour,
        AVG(price) as price,
        SUM(volume) as volume
    FROM price_data
    GROUP BY 1, 2
),
daily_volume AS (
    SELECT
        token_symbol,
        SUM(volume) as volume_24h
    FROM price_data
    WHERE block_time >= NOW() - interval '1' day
    GROUP BY 1
),
latest_prices AS (
    SELECT
        token_symbol,
        FIRST_VALUE(price) OVER (PARTITION BY token_symbol ORDER BY hour DESC) as current_price
    FROM hourly_data
),
price_history AS (
    SELECT
        h.token_symbol,
        ARRAY_AGG(CAST(h.price AS VARCHAR) ORDER BY h.hour DESC) as prices,
        ARRAY_AGG(CAST(h.hour AS VARCHAR) ORDER BY h.hour DESC) as timestamps
    FROM hourly_data h
    GROUP BY h.token_symbol
)
SELECT
    CONCAT(h.token_symbol, '/USDT') as pair_name,
    lp.current_price,
    COALESCE(d.volume_24h, 0) as volume_24h,
    ph.prices as price_history_values,
    ph.timestamps as price_history_times
FROM hourly_data h
LEFT JOIN daily_volume d ON h.token_symbol = d.token_symbol
LEFT JOIN price_history ph ON h.token_symbol = ph.token_symbol
LEFT JOIN latest_prices lp ON h.token_symbol = lp.token_symbol
GROUP BY
    h.token_symbol,
    lp.current_price,
    d.volume_24h,
    ph.prices,
    ph.timestamps
HAVING COUNT(*) >= 24
ORDER BY COALESCE(d.volume_24h, 0) DESC
LIMIT 10;

```

## **Contributing**

Feel free to submit issues and enhancement requests!

## **License**

MIT License - feel free to use this code for your own projects.
