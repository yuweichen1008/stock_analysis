"""
BigQuery helper for the TWS trending pipeline.

Usage:
    bq = BigQueryClient()
    bq.insert_trending(df)          # append today's signal rows
    rows = bq.query_trending(days=7) # fetch last N days as a DataFrame
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Schema matches the columns written by run_taiwan_trending() + a run_date timestamp.
_SCHEMA_FIELDS = [
    ("run_date",      "TIMESTAMP"),
    ("ticker",        "STRING"),
    ("score",         "FLOAT64"),
    ("price",         "FLOAT64"),
    ("MA120",         "FLOAT64"),
    ("MA20",          "FLOAT64"),
    ("RSI",           "FLOAT64"),
    ("bias",          "FLOAT64"),
    ("vol_ratio",     "FLOAT64"),
    ("foreign_net",   "FLOAT64"),
    ("f5",            "FLOAT64"),
    ("f20",           "FLOAT64"),
    ("f60",           "FLOAT64"),
    ("f_zscore",      "FLOAT64"),
    ("short_interest","FLOAT64"),
    ("news_sentiment","FLOAT64"),
    ("last_date",     "STRING"),
]


class BigQueryClient:
    def __init__(
        self,
        project: Optional[str] = None,
        dataset: Optional[str] = None,
        table: Optional[str] = None,
    ):
        try:
            from google.cloud import bigquery
        except ImportError as e:
            raise RuntimeError(
                "google-cloud-bigquery is required: pip install google-cloud-bigquery"
            ) from e

        self.project = project or os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if not self.project:
            raise RuntimeError("Set GCP_PROJECT or GOOGLE_CLOUD_PROJECT environment variable")

        self.dataset = dataset or os.getenv("BQ_DATASET", "tws_dataset")
        self.table   = table   or os.getenv("BQ_TABLE",   "tws_trending")
        self.full_table_id = f"{self.project}.{self.dataset}.{self.table}"

        self._bq = bigquery
        self.client = bigquery.Client(project=self.project)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _schema(self):
        return [
            self._bq.SchemaField(name, ftype)
            for name, ftype in _SCHEMA_FIELDS
        ]

    def ensure_table(self):
        """Create dataset and table if they don't exist."""
        ds_ref = self._bq.DatasetReference(self.project, self.dataset)
        try:
            self.client.get_dataset(ds_ref)
        except Exception:
            ds = self._bq.Dataset(ds_ref)
            ds.location = os.getenv("BQ_LOCATION", "US")
            self.client.create_dataset(ds, exists_ok=True)
            logger.info("Created dataset %s.%s", self.project, self.dataset)

        table_ref = self._bq.TableReference(ds_ref, self.table)
        try:
            self.client.get_table(table_ref)
        except Exception:
            tbl = self._bq.Table(table_ref, schema=self._schema())
            self.client.create_table(tbl, exists_ok=True)
            logger.info("Created table %s", self.full_table_id)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert_trending(self, df):
        """
        Append a trending DataFrame to BigQuery.

        Adds a run_date column (UTC timestamp) if not already present.
        Unknown columns are dropped so the insert always matches the schema.
        """
        import pandas as pd

        self.ensure_table()

        df = df.copy()
        if "run_date" not in df.columns:
            df["run_date"] = datetime.now(tz=timezone.utc).isoformat()

        # Keep only columns that are in the schema
        known = {name for name, _ in _SCHEMA_FIELDS}
        df = df[[c for c in df.columns if c in known]]

        # Cast numeric columns to float so BQ doesn't reject None/NaN
        float_cols = [n for n, t in _SCHEMA_FIELDS if t == "FLOAT64"]
        for col in float_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        job_config = self._bq.LoadJobConfig(
            schema=self._schema(),
            write_disposition=self._bq.WriteDisposition.WRITE_APPEND,
        )
        job = self.client.load_table_from_dataframe(df, self.full_table_id, job_config=job_config)
        job.result()
        logger.info("Inserted %d rows into %s", len(df), self.full_table_id)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query_trending(self, days: int = 7):
        """
        Return trending rows from the last `days` calendar days as a DataFrame.

        Example:
            bq = BigQueryClient()
            df = bq.query_trending(days=7)
            print(df.sort_values('score', ascending=False).head(10))
        """
        sql = f"""
            SELECT *
            FROM `{self.full_table_id}`
            WHERE run_date >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(days)} DAY)
            ORDER BY run_date DESC, score DESC
        """
        import pandas as pd
        try:
            return self.client.query(sql).to_dataframe()
        except Exception as e:
            logger.exception("query_trending failed: %s", e)
            return pd.DataFrame()

    def query_ticker_history(self, ticker: str, days: int = 30):
        """
        Return all historical signal rows for a single ticker.

        Useful for reviewing how a stock has appeared in past scans.
        """
        sql = f"""
            SELECT *
            FROM `{self.full_table_id}`
            WHERE ticker = @ticker
              AND run_date >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(days)} DAY)
            ORDER BY run_date DESC
        """
        job_config = self._bq.QueryJobConfig(
            query_parameters=[self._bq.ScalarQueryParameter("ticker", "STRING", ticker)]
        )
        import pandas as pd
        try:
            return self.client.query(sql, job_config=job_config).to_dataframe()
        except Exception as e:
            logger.exception("query_ticker_history failed: %s", e)
            return pd.DataFrame()
