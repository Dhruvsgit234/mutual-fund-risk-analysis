-- Month-end rolling returns. 1Y is absolute, 3Y/5Y are annualised (CAGR).
-- The look-back NAV is the last NAV on/before the target date, but no more than
-- 7 days stale, so a missing history never silently uses an old price.
-- POW() is registered from Python (common.connect) because SQLite may lack it.
DROP TABLE IF EXISTS rolling_returns;
CREATE TABLE rolling_returns AS
WITH month_end AS (
    SELECT scheme_code, MAX(date) AS date
    FROM nav_daily
    GROUP BY scheme_code, substr(date, 1, 7)
),
base AS (
    SELECT m.scheme_code, m.date, n.nav
    FROM month_end m
    JOIN nav_daily n ON n.scheme_code = m.scheme_code AND n.date = m.date
),
lookback AS (
    SELECT b.scheme_code, b.date, b.nav,
        (SELECT p.nav FROM nav_daily p
          WHERE p.scheme_code = b.scheme_code
            AND p.date <= date(b.date, '-1 year')
            AND p.date >= date(b.date, '-1 year', '-7 day')
          ORDER BY p.date DESC LIMIT 1) AS nav_1y,
        (SELECT p.nav FROM nav_daily p
          WHERE p.scheme_code = b.scheme_code
            AND p.date <= date(b.date, '-3 year')
            AND p.date >= date(b.date, '-3 year', '-7 day')
          ORDER BY p.date DESC LIMIT 1) AS nav_3y,
        (SELECT p.nav FROM nav_daily p
          WHERE p.scheme_code = b.scheme_code
            AND p.date <= date(b.date, '-5 year')
            AND p.date >= date(b.date, '-5 year', '-7 day')
          ORDER BY p.date DESC LIMIT 1) AS nav_5y
    FROM base b
)
SELECT scheme_code, date, nav,
       CASE WHEN nav_1y IS NOT NULL THEN nav / nav_1y - 1.0 END            AS ret_1y,
       CASE WHEN nav_3y IS NOT NULL THEN POW(nav / nav_3y, 1.0 / 3) - 1.0 END AS cagr_3y,
       CASE WHEN nav_5y IS NOT NULL THEN POW(nav / nav_5y, 1.0 / 5) - 1.0 END AS cagr_5y
FROM lookback;
CREATE INDEX IF NOT EXISTS idx_rolling ON rolling_returns(scheme_code, date);
