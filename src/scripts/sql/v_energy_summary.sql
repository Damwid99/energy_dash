CREATE OR REPLACE VIEW v_energy_summary AS
    -- 1. Agregacja danych rzeczywistych do 1 godziny
    WITH actuals_1h AS (
        SELECT 
            DATE_TRUNC('hour', datetime_utc) AS time_utc,
            AVG(pv_actual_pse) AS pv_actual_pse,
            AVG(wind_actual_pse) AS wind_actual_pse,
            AVG(demand_actual_pse) AS demand_actual_pse,
            AVG(exchange_actual_pse) AS exchange_actual_pse,
            AVG(resload_actual_pse) AS resload_actual_pse
        FROM pse_actuals
        GROUP BY DATE_TRUNC('hour', datetime_utc)
    ),
    -- 2. Agregacja cen energii do 1 godziny
    prices_1h AS (
        SELECT 
            DATE_TRUNC('hour', datetime_utc) AS time_utc,
            AVG(fixing_1_pln_mwh) AS fixing_1_pln_mwh,
            AVG(fixing_2_pln_mwh) AS fixing_2_pln_mwh,
            AVG(cen_pln_mwh) AS cen_pln_mwh
        FROM energy_prices
        GROUP BY DATE_TRUNC('hour', datetime_utc)
    )
    -- 3. Łączenie wszystkich trzech źródeł
    SELECT 
        COALESCE(f.issue_datetime_utc, a.time_utc, p.time_utc) AS datetime_utc,
        -- Dane z pse_forecasts
        f.pv_fcst_pse,
        f.wind_fcst_pse,
        f.demand_fcst_pse,
        f.exchange_fcst_pse,
        f.resload_fcst_pse,
        -- Zagregowane dane z pse_actuals
        a.pv_actual_pse,
        a.wind_actual_pse,
        a.demand_actual_pse,
        a.exchange_actual_pse,
        a.resload_actual_pse,
        -- Zagregowane ceny z energy_prices
        p.fixing_1_pln_mwh,
        p.fixing_2_pln_mwh,
        p.cen_pln_mwh
        
    FROM pse_forecasts f
    FULL OUTER JOIN actuals_1h a 
        ON f.issue_datetime_utc = a.time_utc
    FULL OUTER JOIN prices_1h p 
        ON COALESCE(f.issue_datetime_utc, a.time_utc) = p.time_utc;