# S&P 500 Stock Evaluator Backend

This backend provides RESTful APIs for S&P 500 stock analysis and recommendations based on financial indicators using yfinance. 

## Endpoints

- `/stocks [GET]`: Table view of stock recommendations. Optional params: `limit` (int), `search` (str).
- `/stocks/{ticker} [GET]`: Detailed ticker info.

## Quick Start

1. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```

2. **Run the API server:**
   ```
   python main.py
   ```
   The server runs at `http://localhost:8000`. Swagger docs at `/docs`.

3. **API Preview:**
   - Try: `curl http://localhost:8000/stocks`
   - Try: `curl http://localhost:8000/stocks/AAPL`

## File Structure

- `main.py` - Main FastAPI server
- `requirements.txt` - Python dependencies
- `sample_sp500_tickers.txt` - Sample tickers for preview

## Notes

- Data and recommendations are computed live from yfinance and based on simple demo indicators. Refine scoring as needed for production.
- The endpoints support frontend filtering/search as needed.

