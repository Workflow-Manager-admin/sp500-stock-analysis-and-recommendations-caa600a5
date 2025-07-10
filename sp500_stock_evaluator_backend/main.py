"""
Main FastAPI app to serve S&P 500 stock analysis and recommendations.
- /stocks [GET]: Returns table view of S&P 500 stocks with aggregated indicators and recommendations.
- /stocks/{ticker} [GET]: Returns detailed breakdown for a single stock.

Start with: python main.py

Depends on yfinance for data, FastAPI for the REST API.
"""

import os
import uvicorn
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel, Field

# Load sample S&P 500 ticker list for demo/speedup. Expand or update as needed.
SAMPLE_SP500_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",
    "TSLA", "NVDA", "JPM", "V", "UNH"
]

# --- Models ---

class IndicatorBreakdown(BaseModel):
    pe_ratio: Optional[float] = Field(None, description="Price to Earnings Ratio")
    price_to_book: Optional[float] = Field(None, description="Price to Book Ratio")
    debt_to_equity: Optional[float] = Field(None, description="Debt to Equity Ratio")
    return_on_equity: Optional[float] = Field(None, description="Return on Equity (%)")
    profit_margin: Optional[float] = Field(None, description="Profit Margin (%)")
    # Add more indicators as needed

class StockSummary(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol")
    short_name: Optional[str] = Field(None, description="Company name")
    sector: Optional[str] = Field(None, description="Company sector")
    recommendation: str = Field(..., description="System recommendation: BUY/HOLD/SELL")
    indicator_score: float = Field(..., description="Aggregated indicator score, 0-100")
    indicators: IndicatorBreakdown

class StockDetail(StockSummary):
    description: Optional[str] = Field(None, description="Business summary")
    history: Optional[list] = Field(None, description="Historical price/indicator series")  # For future/expansion

# --- FastAPI App Setup ---

app = FastAPI(
    title="S&P 500 Stock Evaluator Backend API",
    description="RESTful API for analyzing S&P 500 stocks with indicator-based BUY/HOLD/SELL recommendations.",
    version="1.0.0"
)

# Allow frontend to request from different origin (for development use)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in prod!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Core Logic ---

def fetch_yf_info(ticker: str):
    """
    Fetches yfinance info dictionary for a ticker. Returns (info, error_message)
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return info, None
    except Exception as e:
        return None, f"Error retrieving {ticker}: {str(e)}"

def score_indicators(info: dict) -> (IndicatorBreakdown, float, str):
    """
    Scores the stock's health based on basic indicators and returns
    (IndicatorBreakdown, aggregate_score, recommendation)
    """
    # Fetch indicators safely
    try:
        pe = info.get("trailingPE")
        pb = info.get("priceToBook")
        debt = info.get("debtToEquity")
        roe = info.get("returnOnEquity")  # As fraction, e.g., 0.21 for 21%
        pm = info.get("profitMargins")    # As fraction, e.g., 0.08 for 8%
    except Exception:
        pe, pb, debt, roe, pm = None, None, None, None, None

    # Score logic (simple, for demo purposes. Refine as required.)
    score = 0
    max_score = 5
    score_details = []

    if pe is not None:
        if pe < 15: score += 1; score_details.append("Good PE")
        elif pe < 25: score += 0.5; score_details.append("Decent PE")
    if pb is not None and pb < 3: score += 1; score_details.append("Good PB")
    if debt is not None and debt < 1: score += 1; score_details.append("Low Debt")
    if roe is not None and roe > 0.1: score += 1; score_details.append("High ROE")
    if pm is not None and pm > 0.1: score += 1; score_details.append("Strong Margin")

    norm_score = (score / max_score) * 100
    if norm_score >= 80:
        reco = "BUY"
    elif norm_score >= 60:
        reco = "HOLD"
    else:
        reco = "SELL"

    indi = IndicatorBreakdown(
        pe_ratio=pe,
        price_to_book=pb,
        debt_to_equity=debt,
        return_on_equity=roe*100 if roe is not None else None,
        profit_margin=pm*100 if pm is not None else None
    )
    return indi, norm_score, reco

# --- API Endpoints ---

# PUBLIC_INTERFACE
@app.get("/stocks", response_model=List[StockSummary], tags=["Stocks"])
def get_stocks(limit: int = 10, search: Optional[str] = None):
    """
    Returns a list of S&P 500 stocks with indicator analysis.
    - Optional limit: Number of stocks to return (default 10).
    - Optional search: Filter by ticker or company name substring.
    """
    results = []
    tickers = SAMPLE_SP500_TICKERS[:limit]
    for tkr in tickers:
        info, err = fetch_yf_info(tkr)
        if err or not info or not info.get("shortName"):
            continue  # Skip unlisted/errored symbols

        if search:
            if search.lower() not in tkr.lower() and search.lower() not in info.get("shortName", "").lower():
                continue  # Not matching search

        indicators, indicator_score, recommendation = score_indicators(info)
        summary = StockSummary(
            ticker=tkr,
            short_name=info.get("shortName"),
            sector=info.get("sector", None),
            indicator_score=indicator_score,
            recommendation=recommendation,
            indicators=indicators
        )
        results.append(summary)
    return results

# PUBLIC_INTERFACE
@app.get("/stocks/{ticker}", response_model=StockDetail, tags=["Stocks"])
def get_stock_detail(ticker: str):
    """
    Returns detailed stock and indicator analysis for one ticker.
    """
    info, err = fetch_yf_info(ticker)
    if err or not info or not info.get("shortName"):
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found or unavailable.")
    indicators, indicator_score, recommendation = score_indicators(info)
    detail = StockDetail(
        ticker=ticker,
        short_name=info.get("shortName"),
        sector=info.get("sector", None),
        indicator_score=indicator_score,
        recommendation=recommendation,
        indicators=indicators,
        description=info.get("longBusinessSummary"),
        history=None  # Expand: can add historic price/indicator chart if needed
    )
    return detail

# Root index for docs/health
# PUBLIC_INTERFACE
@app.get("/", tags=["System"])
def root():
    """
    Returns basic API health/status.
    """
    return {
        "status": "ok",
        "message": "S&P 500 Stock Evaluator Backend is running",
        "endpoints": ["/stocks", "/stocks/{ticker}"],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
