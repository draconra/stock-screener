# Indonesian Stock Exchange (IDX) Screener & Trading Algorithm

A Python and React-based stock screening and quantitative analysis tool for the Indonesian Stock Exchange (IDX). It covers two deliberately separate horizons:

* **Screener** — a 1-5 day scalper. Scans the top liquid IDX stocks, detects high-probability trade setups based on technical momentum indicators, and dynamically calculates optimized buy and sell zones. Tuned to target a **2% - 3% net profit per trade** while safely absorbing standard IDX broker fees (0.15% Buy, 0.25% Sell, 0.04% Levy).
* **Investasi** — a long-term fundamental screener. Scores every liquid IDX company on valuation, profitability, growth, balance-sheet health, and dividends, refreshed monthly from a committed data snapshot (not live). See [`docs/fundamentals-runbook.md`](docs/fundamentals-runbook.md) for how the pipeline works and how to operate it.

These two tabs intentionally do not share scoring logic, caching strategy, or UI vocabulary — see `backend/fundamentals/` for why.

---

## 🚀 Key Features

*   **Real-time Screener:** Scans the IDX market during trading hours to find stocks meeting specific volume and volatility thresholds, gated by real Rupiah turnover value (not just share count) so thinly-traded names don't slip through.
*   **Five-Signal System:** One shared classifier (`services/signal_engine.py`) used by the live screener, the chart markers, and the backtest, producing `SCALP`, `BUY`, `STRONG BUY`, `REVERSAL`, or `SELL`.
*   **Dynamic Calibration:** Uses Average True Range (ATR) to calculate exact buy depths, take-profit targets, and stop-loss levels based on the current volatility of each specific stock.
*   **AI-Powered Optimization:** Integrates with ZhipuAI (GLM-4) to periodically analyze a 6-month historical backtest and dynamically adjust the trading multipliers based on shifting market conditions.
*   **Syariah Compliance Filter:** Automatically tags stocks that are compliant with the Daftar Efek Syariah (DES).
*   **Built-in Backtester:** Includes a robust simulation engine (`simulate.py`) to test configurations against historical data, calculating Win Rate, Expectancy, Risk/Reward, and Max Drawdown.
*   **Fundamental Screener ("Investasi" tab):** Long-term valuation/profitability/growth/health/dividend scoring across the liquid IDX universe, with sector-aware handling (banks are never penalized for lacking a Debt/Equity ratio) and full per-criterion explainability. Data is refreshed monthly offline (GitHub Actions) and served from a committed snapshot — see `backend/fundamentals/`.

---

## 📈 The Trading Strategy

All five signal types below are now classified by one function,
`services/signal_engine.py::classify_signal()` — the chart markers, the live
screener, and the backtest all call it, so a stock labeled `SCALP` means the
same thing everywhere. (This wasn't always true; see `backend/fundamentals/`
sibling docs and the git history around this README section if you're
curious why that distinction is called out explicitly.)

1.  **SCALP:** Price hugging the EMA21 (within 1.0%) at a neutral RSI (45-55) in an uptrend. Checked before the broader BUY conditions below since it's the narrowest setup. Holds ~2 sessions.
2.  **BUY:** Either a momentum pullback (RSI 30-55, elevated volume — on the chart, also requires 1-3 consecutive down days; the live screener works from a point-in-time snapshot and doesn't have that history, so it skips that leg) or a trend-continuation setup with the full EMA9>21>50 stack intact. Holds ~3 sessions.
3.  **STRONG BUY:** The highest-conviction pullback — RSI 30-50 with a volume surge (>2x). On the chart this also requires a 2-3 day pullback; same snapshot-vs-history caveat as BUY. Holds ~5 sessions.
4.  **REVERSAL:** Downtrend, oversold (RSI < 35 or Stochastic %K < 20), price in the **lower 20% of the Bollinger Band range** (not necessarily below the band itself), with a volume spike. Of the four, this is the one with the most direct support in IDX-specific research — individual investors, who dominate IDX turnover, trade contrarian rather than momentum (OJK Working Paper WP/18/04), and momentum itself isn't a significant IDX factor (Li, Wei & Zhang 2023, *Pacific-Basin Finance Journal* 82). Holds ~5 sessions.
5.  **SELL:** Overbought exit signal (RSI > 65, price in the upper 15% of the Bollinger range, elevated volume) — independent of trend direction. Previously only appeared on chart markers; now reachable from the live screener too.

### Profit Targets, Stops & Fees
Sell targets respect a per-signal minimum floor, graduated by how long that signal typically holds: **SCALP 1.5%** (2-day hold), **BUY 2.5%** (3-day), **STRONG BUY / REVERSAL 3.0%** (5-day) — not a single flat number for every signal, since a shorter hold needs a more achievable target. Round-trip fees are ~0.44% (0.15% buy + 0.25% sell + 0.04% levy — the figure used consistently across the screener, calibration, and backtest).

Stop-loss is the tighter of a 1.0×ATR distance and a 3% hard floor below the recommended entry price, computed the same way the backtest (`simulate.py`) evaluates stops, and now surfaced on every buy-type card in the UI (`stop_loss` in the API response).

### Known Limitations
This app's own feature set — RSI/EMA/ATR/Bollinger/Stochastic technicals at a 1-5 day horizon — has been tested directly on IDX by recent academic work: a December 2025 study (*Journal of Risk and Financial Management* 18(12):714) ran linear regression, ridge, random forest and XGBoost on nearly this exact feature set against LQ45 stocks at 5- and 21-day horizons, and found **49-54% directional accuracy** (AUC ~0.50-0.53), with every strategy tested underperforming buy-and-hold after transaction costs. Treat this screener's signals as a structured way to narrow down candidates worth a closer look — not as a high-precision buy/sell oracle. A rigorous walk-forward validation framework (train/test splits, Deflated Sharpe Ratio, Probability of Backtest Overfitting per Bailey & López de Prado) would be needed before trusting any backtested win rate from `simulate.py` at face value; that framework doesn't exist yet in this repo.

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
