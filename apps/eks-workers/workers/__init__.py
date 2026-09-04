"""Product_A EKS worker package (Worker_Alarm / Worker_Finding / Cronjob_Summary).

Importing this package performs no AWS or database I/O. Runtime clients (boto3,
SQLAlchemy engine) are constructed lazily on first use so unit and property
tests can run without external dependencies.
"""
