# Fundamentals pipeline runbook

For the person who comes back to this in three years and has forgotten
everything below. See `backend/fundamentals/` for the code and
`~/.claude/plans/` (or wherever this plan was saved) for the original design
rationale -- this doc is just the operational parts.

## Running a refresh manually

From `backend/`:

```bash
python -m fundamentals.cli refresh              # full universe, commits nothing itself
python -m fundamentals.cli refresh --dry-run     # validate only, writes nothing to data/
python -m fundamentals.cli refresh --limit 20    # small test run
```

The CLI never commits anything to git -- it only writes files under `data/`.
Committing is a separate `git add data/ && git commit && git push` step (the
GitHub Actions workflow does this automatically on the 1st of each month;
locally you do it by hand).

If it exits non-zero, **nothing under `data/` changed** -- check the printed
failure reasons, or look at `data/_staging/report.json` for the full
validation report from the attempt.

## When to run it manually

- The GitHub Actions cron stopped firing (see "GitHub disabled the schedule"
  below).
- Yahoo is rate-limiting GitHub's CI IP range but works fine from your
  connection (`coverage` gate failing in CI, but a local `--limit 20` run
  succeeds).
- You want fresher data than the monthly cadence right now.

## Quarantining a bad snapshot

If a snapshot somehow passed validation but turns out to be bad (a bug in
the validation gates themselves, discovered after the fact): **do not delete
the file.** Add its date to `data/_meta/quarantine.json`:

```json
["2027-03-01"]
```

`store.py` skips quarantined dates when resolving "latest". History stays
intact and auditable; the mistake is documented, not erased.

## What each data-quality threshold means

All thresholds live in `backend/fundamentals/validate.py` (module-level
constants) and `backend/fundamentals/config.py` (screening thresholds, not
data-quality). Quick reference:

| Threshold | Constant | Catches |
|---|---|---|
| Row coverage ≥ 85% | `validate.MIN_COVERAGE` | Yahoo blocking/rate-limiting CI, or yfinance breaking wholesale |
| Field coverage drop ≤ 20pp | `validate.MAX_FIELD_COVERAGE_DROP_PP` | A `.info` key getting renamed or removed upstream |
| Universe size change ≤ 15% | `validate.MAX_UNIVERSE_SIZE_CHANGE_PCT` | TradingView query silently truncating |
| Median market cap change ≤ 10% | `validate.MAX_MEDIAN_MARKET_CAP_CHANGE_PCT` | A currency or scale unit change upstream |
| Big movers ≤ 5% of universe | `validate.MAX_BIG_MOVER_SHARE` | Broad data corruption (individual 50%+ moves are real on IDX small caps) |
| Dividend yield p90 in [1, 20] | `validate.DIV_YIELD_P90_RANGE` | The percent↔fraction unit convention flipping upstream |

If a threshold is firing on genuinely good data (e.g. a real market crash
making median market cap moves exceed 10%), that's a judgment call: either
widen the threshold (with a comment explaining why) or run with `--dry-run`
first, eyeball `data/_staging/report.json`, and if it's legitimate, consider
a one-off manual promotion (there is no CLI flag for "force" by design --
if you need this often, the threshold is wrong, not the process).

## Swapping the data provider

When yfinance eventually breaks for good (Yahoo changes something
incompatible, or the library is abandoned):

1. Write `backend/fundamentals/providers/<new>_provider.py` implementing the
   `FundamentalsProvider` protocol in `providers/base.py`.
2. Change the one import in `cli.py` (`from .providers.yfinance_provider
   import YFinanceProvider`) to the new provider.
3. Nothing else changes -- `score.py`, `store.py`, the API, and every
   historical snapshot are provider-agnostic. `test_provider_isolation.py`
   is what guarantees this stayed true.

Every row already carries `provider` and `provider_version` columns, so a
historical query can tell exactly where the provider changed.

## GitHub disabled the schedule

GitHub auto-disables a scheduled workflow after 60 days with no repository
activity. Symptom: no new commits, `/api/fundamental/meta`'s `data_age_days`
climbing, no error anywhere obvious.

Fix: go to the repo's Actions tab → `fundamentals-refresh` → re-enable it.
Then check that `DATA_PUSH_TOKEN` (a fine-grained PAT, not the default
`GITHUB_TOKEN`) is still valid -- a push made with the default token does
NOT reset the 60-day inactivity clock, which is how this happens in the
first place. Rotate the PAT in repo Settings → Secrets if it expired.

## Vercel deploy shows stale/no fundamentals data

Check `GET /api/fundamental/meta` on the deployed URL:

- `status: "error"` with a `data_dir` path → `vercel.json`'s
  `includeFiles` glob under the `api/index.py` build didn't match. Check the
  paths are relative to the repo root and that `data/snapshots/` actually
  has files committed.
- `status: "success"` but `rows_loaded` is much lower than expected → the
  committed snapshot itself has low coverage; check `data/_meta/latest.json`
  and the corresponding `report.json` from that run (in the GitHub Actions
  run's uploaded artifact, if it was a failed run that somehow still has a
  prior good snapshot serving).

## Renamed ticker breaks a trend chart

IDX tickers occasionally change codes. This looks like a simultaneous
delisting + new listing in `data/universe/registry.csv` and nothing detects
it automatically (deliberately -- see the plan's rationale on avoiding
cleverness here). Fix: add the mapping to
`data/universe/aliases.json`:

```json
{"OLDCODE": "NEWCODE"}
```

`store.trend()` and `store.statements_for()` both resolve aliases before
looking up files, so the trend chart continues instead of truncating.
