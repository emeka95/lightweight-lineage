This fixture is a Redshift-specific integration sample for the lineage tool.

`repo/` contains 20 SQL files covering:

- Spectrum external tables and staged data loaded from S3 with `COPY`.
- Distribution/sort-key DDL and CTAS staging queries using CTEs, window
  functions, and `QUALIFY`.
- Analytics views, a materialized view, and an `UNLOAD` export.
- Stored procedures using `INSERT`, `MERGE`, `CALL`, and materialized-view
  refresh.

The S3 URLs and `IAM_ROLE default` are illustrative; this fixture does not
connect to AWS. `outputs/expected.json` records the expected object and
relationship identities for local regression tests.