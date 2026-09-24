# Dev Log

## Step 1 — Schema design and dataset generation (2026-09-23)

**Built:**
- `data_generator/generate_dataset.py`: orchestrator. Builds the 13 tables in foreign-key order and writes `raw_data/<Table>.csv`.
- Supporting modules:
  - `reference_data.py`: locations, menu, item archetypes, promotion calendar
  - `dimensions.py`: restaurants, menu, pricing history, customers, promotions
  - `transactions.py`: orders and order items
  - `operations.py`: ratings, inventory, wastage
  - `dirty.py`: data-quality injection
  - `common.py`: shared helpers
- Schema documented in `documentation/data_dictionary.md`.

**Run:**
```
.venv/bin/python data_generator/generate_dataset.py --scale 1.0          # default, seed 42
.venv/bin/python data_generator/generate_dataset.py --scale 5.0          # ~5.3M order lines
.venv/bin/python data_generator/generate_dataset.py --clean              # skip dirty-data injection
```
- `--scale` multiplies the number of customers, orders, order lines and ratings.
- Inventory stays at one row per item per location per day, so its row count does not scale. Its quantities do, because they come from actual sales.
- Scale 1 runs in about 30–110 s, depending on the machine.
- Scale 5 took 88 s and peaked at about 3.5 GB of RAM.

**Setup note:** the machine had no pip or venv support (`python3.14-venv` is not installed). The project `.venv` was created with `--without-pip`, and pip was bootstrapped with `get-pip.py`. Dependencies are in `requirements.txt`.

**Assumptions:**
- The chain is set in Pakistan: 25 locations in 11 cities.
- Prices are in PKR, with provincial sales tax.
- The spec's Monsoon season and Fri–Sun weekend pointed to this setting.
- Ramadan (March 2025) moves order hours to the evening.
- The Eid days, Independence Day and year-end get demand spikes.

**Output at scale 1.0 (seed 42), including injected duplicates:**

| Table | Rows |
|---|---|
| Restaurants | 25 |
| Menu_Categories | 14 |
| Menu_Items | 160 |
| Pricing_History | 959 (2–5 chain-wide price points per item) |
| Customers | 55,000 |
| Promotions | 20 |
| Promotion_Items | 1,316 |
| Promotion_Locations | 424 |
| Orders | 196,547 (194,601 unique) |
| Order_Items | 1,070,114 (1,059,519 unique; 1,028,791 with every corrupted row removed) |
| Ratings | 105,000 |
| Inventory | 1,251,246 |
| Wastage | 60,290 |

**Patterns built into the data (none of them are labelled in the CSVs):**
- **Weekends:** Fri–Sun is about 17% of weekly orders per day, against about 12% on weekdays. Downtown locations are flatter.
- **Peak hours:** 12–14 and 19–22.
- **Seasonality:** monthly seasonality plus seasonal items (Summer, Winter, Monsoon).
- **Growth:** about 8% growth over the year.
- **Location spread:** order volume ranges about 4.5x between the quietest and busiest location. Each location also has its own sales mix and service quality, so the same item sells and rates differently by location.
- **Customer archetypes:** loyal high-value, frequent, promotion-driven, churned, new (October–December signups) and occasional. They show up in frequency, recency and spend. Median orders per customer is 2, the 99th percentile about 20, and about 7% of customers never ordered.
- **Item archetypes:**
  - High-volume, low-margin items: margin about 31% against a median of 59%.
  - High-margin, low-volume items: margin about 84%, volume rank around 130 of 160.
  - High-wastage popular items: the top 6 items by wastage cost.
  - Poorly rated items: average rating about 2.0 against 3.7 overall.
  - Promotion-dependent items: about 73% of their units sell on promotion orders, against 19% for all items.
- **Promotion trap:** "August BOGO Blast" (PROMO012). Compared with July, August has:
  - orders +58% and unique customers +38%
  - gross margin down from 57.4% to 53.9%
  - wastage cost about 3.5x, because kitchens over-prepare for the promotion
- **Price changes:** 7 items get a mid-year price rise of 18–28%, and their demand falls (e.g. Mutton Biryani, about 46 → 30 units a day). 3 items get a 15% cut, and their demand rises.
- **Cancellations:** about 4.2% of orders are cancelled, more on delivery channels. This is real data, not injected.

**Consistency checks on the clean build (`--clean`, no injection): zero violations.**
- Order subtotal, discount and total match the order's lines.
- Order line unit prices match the Pricing_History price in effect for that location and date.
- `closing_stock = opening + received − consumed − wasted` on every Inventory row.
- Wastage never exceeds prepared quantity.

**Injected dirtiness:**
- Full row-level log: `reports/dirty_injection_log.csv`
- Per-rule counts: `reports/dirty_injection_summary.csv`
- Each rule uses its own rows within a table.

| Table | Rule (column) | Rows |
|---|---|---|
| Customers | invalid_date (signup_date) | 275 |
| Customers | orphan_foreign_key (home_location_id) | 275 |
| Menu_Items | invalid_price (base_price) | 3 |
| Pricing_History | invalid_price (price) | 14 |
| Orders | missing_value (customer_id) | 1,946 |
| Orders | orphan_foreign_key (customer_id) | 973 |
| Orders | orphan_foreign_key (location_id) | 584 |
| Orders | invalid_date (order_datetime) | 973 |
| Orders | discount_exceeds_subtotal | 973 |
| Orders | duplicate_row | 1,946 |
| Order_Items | missing_value (item_id) | 5,298 |
| Order_Items | negative_quantity | 5,298 |
| Order_Items | invalid_price (unit_price) | 3,179 |
| Order_Items | orphan_foreign_key (order_id) | 3,179 |
| Order_Items | orphan_foreign_key (item_id) | 3,179 |
| Order_Items | duplicate_row | 10,595 |
| Ratings | missing_value (rating_value) | 1,575 |
| Ratings | rating_out_of_range | 1,050 |
| Ratings | invalid_date (rating_date) | 525 |
| Ratings | orphan_foreign_key (location_id) | 525 |
| Ratings | orphan_foreign_key (customer_id) | 315 |
| Inventory | inconsistent_unit | 12,512 |
| Inventory | orphan_foreign_key (item_id) | 3,754 |
| Wastage | wastage_exceeds_prepared | 603 |
| Wastage | inconsistent_unit | 1,206 |
| Wastage | invalid_date | 301 |
| Wastage | missing_value (item_id) | 301 |
| Wastage | orphan_foreign_key (location_id) | 301 |

**Known limitations:**
- Promotions are not tied to order channels. For example, the "App Exclusive Fest" can apply to dine-in orders.
- Corrupted rows keep the other columns' original values, so a negative-quantity line still has its original `line_total`.

**Next step:** Spark ingestion, schema validation, cleaning and Parquet conversion.

## Step 2 — Spark ingestion, data quality, cleaning, integration (2026-09-24)

**Built:**
- `spark_jobs/schemas.py`: explicit `StructType` per table (13/13), plus a raw all-string variant used for the type-validation check.
- `spark_jobs/spark_utils.py`: Spark session factory, `JobLogger` (console + `reports/spark_execution_log_<job>.txt`, with a `timer()` context manager for stage durations), single-file CSV/JSON writers.
- `spark_jobs/01_ingest_and_validate.py`: loads all 13 tables with explicit schemas; schema-inference demo (`Restaurants`, `inferSchema=True`, logged side by side with the declared schema); data-type validation (typed load vs. raw-string load diff on the 4 date/timestamp columns with injected malformed values); large-file load (`Order_Items` direct) plus a multi-file ingestion demo (joins `Order_Items` to `Orders` for the month, writes it partitioned by `order_month`, then reads that directory back as one DataFrame — 39 part files); referential-integrity orphan counts via left-anti join (not `.isin()` — see gotcha below); the full SRS Step-4 issue checklist. Writes `reports/data_quality_report.md` (+ a `.csv` twin for the tests) with a cross-check against `reports/dirty_injection_summary.csv`.
- `spark_jobs/02_clean.py`: applies `documentation/data_quality_rules.md` per table — dedupe (`Orders`, `Order_Items`), price correction from `Pricing_History` (`Menu_Items.base_price`, `Order_Items.unit_price`), unit normalization (`Inventory`/`Wastage`), and quarantine for everything else. Writes `processed_data/<Table>.csv`, `processed_data/quarantine/<Table>.csv` (with `quarantine_reason`), `reports/cleaning_log.csv`, `reports/cleaning_row_counts.csv`.
- `spark_sql/integration_queries.sql`: the 10 required joins plus `fact_order_line`, the order-line-grain base fact table (left join outward from `Order_Items`). Parsed and run by `spark_jobs/03_integrate_and_store.py` via `-- @name:` markers.
- `spark_jobs/03_integrate_and_store.py`: registers the cleaned tables as temp views, runs all 11 queries, writes `fact_order_line` to `parquet_data/fact_order_line/` partitioned by `order_year`/`order_month`; `Orders`, `Inventory`, `Wastage` to `parquet_data/<table>/` partitioned by `year`/`month`; `Order_Items` likewise (joined to `Orders` for the date). Writes `Menu_Categories`/`Promotions` to `processed_data/*.json` as the storage-format demo.
- `documentation/data_quality_rules.md`: the cleaning rules, written before implementation, per rule.
- `tests/`: `test_schema.py`, `test_data_quality.py`, `test_cleaning.py`, `test_joins.py`, `test_parquet_roundtrip.py` — 20 tests, all passing.

**Run (in order):**
```
.venv/bin/python spark_jobs/01_ingest_and_validate.py
.venv/bin/python spark_jobs/02_clean.py
.venv/bin/python spark_jobs/03_integrate_and_store.py
.venv/bin/python -m pytest tests/ -v
```
Scale-1 seed-42 dataset: ingest+validate ~75s, clean ~4 min, integrate ~3 min, tests ~85s.

**Row counts, before -> after cleaning (scale 1.0):**

| Table | Before | After | Removed |
|---|---|---|---|
| Pricing_History | 959 | 945 | 14 |
| Customers | 55,000 | 54,450 | 550 |
| Orders | 196,547 | 187,228 | 9,319 |
| Order_Items | 1,070,114 | 1,002,824 | 67,290 |
| Ratings | 105,000 | 97,121 | 7,879 |
| Inventory | 1,251,246 | 1,247,492 | 3,754 |
| Wastage | 60,290 | 58,787 | 1,503 |

Removed counts run higher than the Step 1 injection counts alone because quarantine cascades: e.g. a `Customers` row quarantined for a bad `signup_date` or invalid `home_location_id` makes every `Orders` row referencing it an orphan too, which in turn cascades to `Order_Items` and `Ratings`. This is intentional — it's what a real FK-aware cleaning pipeline does — and is called out in `reports/data_quality_report.md`'s cross-check section, which compares Step 2's detected counts against Step 1's injected counts on the *raw* data (where they match almost exactly, see below).

**Data quality cross-check:** on the raw data, Step 2's detected counts match Step 1's injected counts almost exactly (see `reports/data_quality_report.md`). The only gaps: `Order_Items` duplicate count runs +68 high (the (order_id, item_id) dedupe key also catches unrelated rows that share an order_id and both have a null item_id), `Wastage.wastage_exceeds_prepared` runs -3 low (a few Wastage rows have no matching Inventory row to compare against), and `Orders.cancelled_transaction_count` (8,262 rows, 4.2%) has no Step 1 counterpart by design — cancellations are real business data, not injected.

**Gotchas hit and fixed:**
- The machine's global `HADOOP_CONF_DIR` points `fs.defaultFS` at an HDFS namenode that isn't running (`hdfs://localhost:9000`), so any local-path read/write failed with `ConnectException`. Fixed by pinning `spark.hadoop.fs.defaultFS=file:///` in `get_spark()` — this project only touches local directories.
- Orphan-FK checks originally collected the parent table's keys into a Python list and used `.isin(list(...))`. With parent tables up to ~195k rows, the resulting IN-list expression made the driver choke (heartbeat timeouts, effectively hung). Rewrote as a left join against distinct parent keys (`with_orphan_flag()` in `02_clean.py`) — same result, no driver-side blowup.
- `02_clean.py` referenced `cleaned["Orders"]` etc. repeatedly across later table-cleaning blocks without caching, so Spark recomputed the entire upstream lineage (window functions and all) on every later action — one run took over 10 minutes before being fixed. Fixed by `.cache()` + an immediate `.count()` right after each `cleaned[table]` is finalized.
- Spark's CSV writer serializes `TimestampType` as ISO-8601 with a `T`/`Z` (`2025-01-01T00:12:52.000Z`) by default, which doesn't match the `yyyy-MM-dd HH:mm:ss` format the loader's `timestampFormat` option expects on reload — every `Orders.order_datetime` value came back null after a write/read round-trip, silently collapsing the year/month partitioning to a single `__HIVE_DEFAULT_PARTITION__` bucket. Fixed by pinning `dateFormat`/`timestampFormat` on write too (`_write_single_csv()`), so cleaned CSVs round-trip through the same schema they were written with.
- The unit-normalization map only covered the variants listed in the data dictionary's example (`kgs`, `KG`, `ltr`, ...) and missed variants actually present in the generated data (`Pcs`, `PCS`, `kilogram`, `Liters`) — caught by `tests/test_cleaning.py::test_units_normalized` failing with 4,656 un-normalized rows. Fixed by checking the raw value distribution directly and extending `UNIT_MAP`.

**Next step:** feature engineering (revenue, margin, RFM, etc.) on top of `parquet_data/fact_order_line/`.
