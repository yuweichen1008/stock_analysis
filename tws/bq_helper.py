import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BigQueryClient:
    def __init__(self, project: Optional[str] = None, dataset: Optional[str] = None, table: Optional[str] = None):
        try:
            from google.cloud import bigquery
        except Exception as e:
            raise RuntimeError("google-cloud-bigquery is required to use BigQueryClient") from e

        self.project = project or os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.dataset = dataset or os.getenv("BQ_DATASET", "tws_dataset")
        self.table = table or os.getenv("BQ_TABLE", "tws_trending")

        self.client = bigquery.Client(project=self.project)
        self.full_table_id = f"{self.project}.{self.dataset}.{self.table}"

    def ensure_dataset(self):
        from google.cloud import bigquery

        ds_ref = bigquery.DatasetReference(self.project, self.dataset)
        try:
            self.client.get_dataset(ds_ref)
        except Exception:
            ds = bigquery.Dataset(ds_ref)
            ds.location = os.getenv("BQ_LOCATION", "US")
            self.client.create_dataset(ds, exists_ok=True)

    def insert_trending(self, df):
        """Insert pandas DataFrame into BigQuery table (append)."""
        from google.cloud import bigquery
        self.ensure_dataset()

        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

        # Convert dataframe so BigQuery can infer schema
        job = self.client.load_table_from_dataframe(df, self.full_table_id, job_config=job_config)
        job.result()
        logger.info("Inserted %d rows into %s", job.output_rows, self.full_table_id)
