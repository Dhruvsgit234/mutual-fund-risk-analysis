-- Daily return and drawdown per fund, using window functions.
DROP VIEW IF EXISTS v_daily_returns;
CREATE VIEW v_daily_returns AS
SELECT scheme_code,
       date,
       nav,
       nav / LAG(nav) OVER (PARTITION BY scheme_code ORDER BY date) - 1.0 AS ret
FROM nav_daily;

DROP VIEW IF EXISTS v_drawdown;
CREATE VIEW v_drawdown AS
SELECT scheme_code,
       date,
       nav,
       MAX(nav) OVER (PARTITION BY scheme_code ORDER BY date
                      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_peak,
       nav / MAX(nav) OVER (PARTITION BY scheme_code ORDER BY date
                      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) - 1.0 AS drawdown
FROM nav_daily;
