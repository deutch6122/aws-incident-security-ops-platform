"""Sample data seed scripts for the AWS Incident & Security Operations Platform.

These scripts generate NON-SENSITIVE, DUMMY sample data for the dev/MVP
environment (Task 18.1). They are safe by default: every script runs in
dry-run (print-only) mode unless ``--execute`` is passed explicitly.

Design principles (see scripts/README.md):

* **boto3 is imported lazily** — importing this package performs no AWS I/O and
  requires no AWS credentials. The boto3 client is only created inside the
  ``--execute`` path.
* **dry-run is the default** — nothing is sent to AWS unless the operator opts
  in with ``--execute`` (alias ``--no-dry-run``).
* **dummy only** — payloads contain no real ARNs, account IDs, tokens, secrets,
  or real domains. Placeholders are used throughout.
* **A -> B one-way** — the report / public-status seed targets Product_B
  (DynamoDB / S3) only; it never writes to Product_A resources.
"""

from __future__ import annotations

__all__ = ["common"]
