# Indonesian Stock Exchange (IDX) Screener & Trading Algorithm

A Python and React-based stock screening and quantitative analysis tool for the Indonesian Stock Exchange (IDX). It covers two deliberately separate horizons:

* **Screener** — a 1-5 day scalper. Scans the top liquid IDX stocks, detects high-probability trade setups based on technical momentum indicators, and dynamically calculates optimized buy and sell zones. Tuned to target a **2% - 3% net profit per trade** while safely absorbing standard IDX broker fees (0.15% Buy, 0.25% Sell, 0.04% Levy).
* **Investasi** — a long-term fundamental screener. Scores every liquid IDX company on valuation, profitability, growth, balance-sheet health, and dividends, refreshed monthly from a committed data snapshot (not live). See [`docs/fundamentals-runbook.md`](docs/fundamentals-runbook.md) for how the pipeline works and how to operate it.

These two tabs intentionally do not share scoring logic, caching strategy, or UI vocabulary — see `backend/fundamentals/` for why.

---

## 🚀 Key Features

*   **Real-time Screener:** Scans the IDX market during trading hours to find stocks meeting specific volume and volatility thresholds.
*   **Four-Signal System:** Automatically classifies technical setups into `SCALP`, `BUY`, `STRONG BUY`, or `REVERSAL` signals.
*   **Dynamic Calibration:** Uses Average True Range (ATR) to calculate exact buy depths and take-profit targets based on the current volatility of each specific stock.
*   **AI-Powered Optimization:** Integrates with ZhipuAI (GLM-4) to periodically analyze a 6-month historical backtest and dynamically adjust the trading multipliers based on shifting market conditions.
*   **Syariah Compliance Filter:** Automatically tags stocks that are compliant with the Daftar Efek Syariah (DES).
*   **Built-in Backtester:** Includes a robust simulation engine (`simulate.py`) to test configurations against historical data, calculating Win Rate, Expectancy, Risk/Reward, and Max Drawdown.
*   **Fundamental Screener ("Investasi" tab):** Long-term valuation/profitability/growth/health/dividend scoring across the liquid IDX universe, with sector-aware handling (banks are never penalized for lacking a Debt/Equity ratio) and full per-criterion explainability. Data is refreshed monthly offline (GitHub Actions) and served from a committed snapshot — see `backend/fundamentals/`.

---

## 📈 The Trading Strategy

The underlying logic relies on mean reversion within established trends, focusing on high-probability over high-yield:

1.  **SCALP:** Triggers when a stock in a confirmed uptrend dips briefly to touch the EMA21 support line (with RSI 45-55). Optimized for quick 1-2 day holds.
2.  **BUY:** Standard momentum pullback. Triggers when an uptrending stock experiences 1-3 consecutive down days with elevated volume and an RSI of 30-55.
3.  **STRONG BUY:** High conviction pullback. Triggers when the stock pulls back into a highly optimal oversold zone (RSI 30-50) while maintaining strong trading volume.
4.  **REVERSAL:** Catches oversold bounces. Triggers when a stock drops below the lower Bollinger Band, becomes deeply oversold (RSI < 35), and shows a sudden spike in volume (indicating smart money buying the dip).

### Profit Targets & Fees
The algorithm enforces a hard minimum target floor of **3.5% gross profit** on every trade. This ensures that after paying the ~0.44% IDX round-trip trading fees, the trader walks away with a net profit of around 2.5% to 3.0%. 

Stop losses are set dynamically based on a multiple of the stock's ATR, generally favoring wider stops to prevent premature exits due to normal market noise.

---

## 🤖 AI Dynamic Calibration

The market is constantly changing. To prevent the static ATR multipliers from becoming obsolete, the backend leverages a Large Language Model (GLM-4 via ZhipuAI). 

On startup, the system:
1. Runs a statistical backtest on the top 20 most liquid IDX stocks over the last 6 months.
2. Calculates the Maximum Favorable Excursion (MFE) and Maximum Adverse Excursion (MAE) for every signal generated.
3. Sends this raw data to the GLM-4 AI model via a secure prompt.
4. The AI analyzes the data and replies with an optimized JSON configuration, fine-tuning the `buy_depth`, `target_lo`, and `target_hi` variables to adapt to the current market regime.

---

## 🛠️ Project Structure

```text
stock-screener/
│
├── backend/                  # Python FastAPI Server
│   ├── api.py                # Main server entrypoint and REST endpoints
│   ├── screener_service.py   # TradingView scanner logic (scalper)
│   ├── simulate.py           # Historical backtesting engine (scalper)
│   ├── requirements.txt      # Python dependencies (pinned)
│   ├── requirements-dev.txt  # + pytest, for running fundamentals/tests/
│   ├── pytest.ini
│   ├── .env                  # Environment variables (GLM_API_KEY)
│   ├── services/             # Scalper business logic
│   │   ├── indicators.py     # Technical indicator math (RSI, ATR, EMAs, etc.)
│   │   ├── calibration.py    # Dynamic targets and AI integration
│   │   ├── news.py           # Financial news fetcher
│   │   └── syariah.py        # Syariah compliance checker (shared with Investasi tab)
│   └── fundamentals/         # Long-term screener: schema, scoring, data pipeline
│       ├── cli.py            # `python -m fundamentals.cli refresh` -- see docs/fundamentals-runbook.md
│       ├── providers/        # yfinance_provider.py is the ONLY module allowed to import yfinance
│       ├── score.py          # gates + 5-pillar scoring engine
│       ├── store.py          # stdlib-only serverless read path
│       └── tests/            # 74 offline tests, fixture-based
│
├── data/                      # Committed fundamentals snapshots (see fundamentals/writer.py)
├── docs/
│   └── fundamentals-runbook.md
│
└── frontend/                  # React UI
    └── src/components/
        ├── ScreenerTab.tsx, StockCard.tsx, ...      # scalper
        └── InvestTab.tsx, FundamentalCard.tsx, ...  # long-term screener
```

---

## 💻 Installation & Setup

### Prerequisites
* Python 3.9+
* Node.js (for the frontend)
* An active ZhipuAI API Key for the AI Calibration

### Backend Setup
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the `backend/` directory and add your GLM API key:
   ```env
   GLM_API_KEY=your_api_key_here
   ```
4. Start the FastAPI server:
   ```bash
   python api.py
   ```
   *(The API will be available at `http://localhost:8000`)*

### Running a Backtest
To verify the current configuration against historical data, run the simulator from the backend directory:
```bash
python simulate.py
```
This will output a detailed comparison table showing the Win Rate, Expectancy, and Sharpe Ratio of various configurations.

### Fundamental Screener ("Investasi" tab)

This tab reads from a pre-computed snapshot under `data/` — it does **not** hit
yfinance at request time. To generate or refresh that snapshot locally:

```bash
cd backend
pip install -r requirements-dev.txt   # adds pytest on top of requirements.txt
python -m pytest fundamentals/tests/ -v   # 74 tests, offline, ~1s
python -m fundamentals.cli refresh --dry-run --limit 20   # smoke test, writes nothing
python -m fundamentals.cli refresh                        # full run, ~8-10 min, writes data/
```

In production this runs monthly via `.github/workflows/fundamentals-refresh.yml`.
Full details, including what each data-quality threshold catches and how to
recover from a stalled pipeline, are in
[`docs/fundamentals-runbook.md`](docs/fundamentals-runbook.md).
