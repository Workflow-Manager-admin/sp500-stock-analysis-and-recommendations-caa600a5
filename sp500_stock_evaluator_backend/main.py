"""
sp500_stock_evaluator_backend - RESTful API for S&P 500 stock analysis.

This FastAPI application analyzes S&P 500 stocks using yfinance and exposes:
- /stocks [GET]: List of S&P 500 stocks with buy/hold/sell recommendations and scores.
- /stocks/{ticker} [GET]: Detailed metrics and score breakdown for a single ticker.

Returns JSON responses including indicator breakdown and recommendation.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import yfinance as yf
import uvicorn
import pandas as pd

# API Metadata & Tagging
app = FastAPI(
    title="S&P 500 Stock Evaluator API",
    description="Fetches S&P 500 stock data, evaluates financial health metrics, and provides buy/hold/sell recommendations.",
    version="1.0.0",
    openapi_tags=[
        {
            "name": "stocks",
            "description": "Endpoints for retrieving S&P 500 stock recommendations and details",
        }
    ],
)

# -- Models --

class IndicatorBreakdown(BaseModel):
    """Breakdown of financial indicators contributing to the score."""
    pe_ratio: Optional[float] = Field(None, description="Trailing P/E ratio")
    profit_margin: Optional[float] = Field(None, description="Net profit margin (%)")
    debt_to_equity: Optional[float] = Field(None, description="Debt/Equity ratio")
    roe: Optional[float] = Field(None, description="Return on Equity (%)")
    dividend_yield: Optional[float] = Field(None, description="Dividend Yield (%)")
    current_ratio: Optional[float] = Field(None, description="Current (liquidity) Ratio")

class StockScore(BaseModel):
    """Score summary for a stock."""
    ticker: str = Field(..., description="Stock ticker symbol")
    name: str = Field(..., description="Company name")
    score: float = Field(..., description="Overall score, 0-100")
    recommendation: str = Field(..., description="BUY/HOLD/SELL signal")
    breakdown: IndicatorBreakdown = Field(..., description="Contributing indicator values")

class StockListResponse(BaseModel):
    """List response for /stocks endpoint."""
    stocks: List[StockScore] = Field(..., description="List of evaluated S&P 500 stocks")

class StockDetailResponse(BaseModel):
    """Detailed response for an individual stock."""
    ticker: str
    name: str
    score: float
    recommendation: str
    indicator_breakdown: IndicatorBreakdown
    raw_data: Dict

# -- Constants --

SP500_TICKERS_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
INDICATOR_WEIGHTS = {
    'pe_ratio': -1,         # negative weight: lower better (undervalued)
    'profit_margin': 2,
    'debt_to_equity': -1,   # negative weight: lower better
    'roe': 2,
    'dividend_yield': 1,
    'current_ratio': 1,
}

# -- Utilities & Business Logic --

def get_sp500_tickers() -> pd.DataFrame:
    """Fetch S&P 500 tickers and company names from Wikipedia."""
    tables = pd.read_html(SP500_TICKERS_URL)
    df = tables[0]
    df = df[['Symbol', 'Security']]  # Ticker and Name columns
    df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False)  # Match Yahoo Finance format
    return df

def fetch_stock_fundamentals(ticker: str):
    """Fetch relevant fundamental data for a given ticker."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return {
            "pe_ratio": info.get("trailingPE"),
            "profit_margin": info.get("profitMargins", 0) * 100 if info.get("profitMargins") else None,
            "debt_to_equity": info.get("debtToEquity"),
            "roe": info.get("returnOnEquity", 0) * 100 if info.get("returnOnEquity") else None,
            "dividend_yield": info.get("dividendYield", 0) * 100 if info.get("dividendYield") else None,
            "current_ratio": info.get("currentRatio"),
            "name": info.get("shortName") or info.get("longName") or ticker,
            "raw": info,
        }
    except Exception:
        return None

def score_stock(fundamentals: dict) -> (float, str, IndicatorBreakdown):
    """Calculate a stock's health score and recommendation."""
    # Guard: missing data is penalized (score is lower)
    breakdown = IndicatorBreakdown(
        pe_ratio=fundamentals.get("pe_ratio"),
        profit_margin=fundamentals.get("profit_margin"),
        debt_to_equity=fundamentals.get("debt_to_equity"),
        roe=fundamentals.get("roe"),
        dividend_yield=fundamentals.get("dividend_yield"),
        current_ratio=fundamentals.get("current_ratio"),
    )

    # -- Raw values to normalized points (0-100)
    scoring = 0
    max_score = 0
    # P/E Ratio: ideal 10-25 (lower generally better, but negative or near-zero not good)
    pe = breakdown.pe_ratio
    if pe is not None and pe > 0:
        if pe < 10: pe_score = 100
        elif pe < 16: pe_score = 75
        elif pe < 25: pe_score = 55
        elif pe < 40: pe_score = 35
        else: pe_score = 10
        scoring += pe_score * abs(INDICATOR_WEIGHTS['pe_ratio'])
        max_score += 100 * abs(INDICATOR_WEIGHTS['pe_ratio'])
    else:
        max_score += 100 * abs(INDICATOR_WEIGHTS['pe_ratio'])

    # Profit Margin: higher is better
    pm = breakdown.profit_margin
    if pm is not None:
        if pm > 20: pm_score = 100
        elif pm > 10: pm_score = 70
        elif pm > 0: pm_score = 45
        else: pm_score = 10
        scoring += pm_score * INDICATOR_WEIGHTS['profit_margin']
        max_score += 100 * INDICATOR_WEIGHTS['profit_margin']
    else:
        max_score += 100 * INDICATOR_WEIGHTS['profit_margin']

    # Debt to Equity: lower is better (below 1 optimal)
    dte = breakdown.debt_to_equity
    if dte is not None and dte >= 0:
        if dte < 0.5: dte_score = 100
        elif dte < 1: dte_score = 80
        elif dte < 2: dte_score = 55
        elif dte < 4: dte_score = 25
        else: dte_score = 5
        scoring += dte_score * abs(INDICATOR_WEIGHTS['debt_to_equity'])
        max_score += 100 * abs(INDICATOR_WEIGHTS['debt_to_equity'])
    else:
        max_score += 100 * abs(INDICATOR_WEIGHTS['debt_to_equity'])

    # ROE: higher (positive) is better
    roe = breakdown.roe
    if roe is not None:
        if roe > 25: roe_score = 100
        elif roe > 15: roe_score = 75
        elif roe > 0: roe_score = 55
        else: roe_score = 10
        scoring += roe_score * INDICATOR_WEIGHTS['roe']
        max_score += 100 * INDICATOR_WEIGHTS['roe']
    else:
        max_score += 100 * INDICATOR_WEIGHTS['roe']

    # Dividend Yield: 2-5% is good, higher can be warning, zero is not necessarily bad
    dy = breakdown.dividend_yield
    if dy is not None:
        if dy > 7 or dy < 0: dy_score = 10
        elif dy >= 5: dy_score = 65
        elif dy >= 2: dy_score = 90
        elif dy > 0: dy_score = 65
        else: dy_score = 40
        scoring += dy_score * INDICATOR_WEIGHTS['dividend_yield']
        max_score += 100 * INDICATOR_WEIGHTS['dividend_yield']
    else:
        max_score += 100 * INDICATOR_WEIGHTS['dividend_yield']

    # Current Ratio: measure of liquidity (>1.2 good, 1.5-3 ideal, >5 bad sign)
    cr = breakdown.current_ratio
    if cr is not None and cr > 0:
        if cr > 5: cr_score = 10
        elif cr >= 3: cr_score = 70
        elif cr >= 1.5: cr_score = 100
        elif cr >= 1.2: cr_score = 80
        elif cr >= 1: cr_score = 65
        else: cr_score = 10
        scoring += cr_score * INDICATOR_WEIGHTS['current_ratio']
        max_score += 100 * INDICATOR_WEIGHTS['current_ratio']
    else:
        max_score += 100 * INDICATOR_WEIGHTS['current_ratio']

    # Final normalization
    final_score = round((scoring / max_score) * 100, 1) if max_score > 0 else 0.0

    # Recommendation thresholds
    if final_score >= 80:
        recommendation = "BUY"
    elif final_score >= 60:
        recommendation = "HOLD"
    else:
        recommendation = "SELL"

    return final_score, recommendation, breakdown

# -- Caching (for demo/small-scale only) --

STOCK_CACHE = {}

def get_stock_result(ticker: str) -> StockScore:
    """Get a StockScore for a ticker, with simple in-memory caching."""
    if ticker in STOCK_CACHE:
        return STOCK_CACHE[ticker]
    fundamentals = fetch_stock_fundamentals(ticker)
    if not fundamentals:
        raise HTTPException(status_code=404, detail="Failed to fetch stock data.")
    score, recommendation, breakdown = score_stock(fundamentals)
    result = StockScore(
        ticker=ticker,
        name=fundamentals.get("name", ticker),
        score=score,
        recommendation=recommendation,
        breakdown=breakdown,
    )
    STOCK_CACHE[ticker] = result
    return result


# -- API Endpoints --

# PUBLIC_INTERFACE
@app.get("/stocks", 
         response_model=StockListResponse,
         tags=["stocks"], 
         summary="List S&P 500 stocks with recommendations")
async def list_stocks(limit: int = 50):
    """
    Retrieve a list of S&P 500 stocks with computed financial health scores and buy/hold/sell recommendations.

    - **limit**: Maximum number of stocks to return (default 50, max 500).
    """
    try:
        df = get_sp500_tickers()
        stocks = []
        for idx, row in df.iterrows():
            if len(stocks) >= limit: break
            ticker = row["Symbol"]
            try:
                stock_score = get_stock_result(ticker)
                stocks.append(stock_score)
            except Exception:
                continue  # Could add per-ticker error handling/logging here
        return StockListResponse(stocks=stocks)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(ex)}")

# PUBLIC_INTERFACE
@app.get("/stocks/{ticker}", 
         response_model=StockDetailResponse,
         tags=["stocks"], 
         summary="Detailed metrics for a single stock")
async def get_stock_details(ticker: str):
    """
    Retrieve detailed financial indicator breakdown and score for a specific S&P 500 ticker.

    - **ticker**: (str) Stock symbol, e.g., 'AAPL'.
    """
    ticker = ticker.upper()
    df = get_sp500_tickers()
    if ticker not in df['Symbol'].values:
        raise HTTPException(status_code=404, detail="Ticker not found in S&P 500.")
    fundamentals = fetch_stock_fundamentals(ticker)
    if not fundamentals:
        raise HTTPException(status_code=404, detail="Stock data not found.")
    score, recommendation, breakdown = score_stock(fundamentals)
    return StockDetailResponse(
        ticker=ticker,
        name=fundamentals.get("name", ticker),
        score=score,
        recommendation=recommendation,
        indicator_breakdown=breakdown,
        raw_data=fundamentals["raw"],
    )

# PUBLIC_INTERFACE
@app.get("/", include_in_schema=False)
def read_root():
    """Welcome page - brief API description."""
    return {"message": "Welcome to the S&P 500 Stock Evaluator API! See /docs for OpenAPI documentation."}

# PUBLIC_INTERFACE
@app.get("/health", tags=["utility"])
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}

# -- Entrypoint --

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
