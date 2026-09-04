"""Portal_API (Product_B) Lambda application package.

The package holds the API Gateway HTTP API v2 handler, a DynamoDB access layer
behind repository Protocols (DynamoDB and in-memory fake implementations), JWT
claim verification, and the status/report read APIs.

Importing this package performs no AWS I/O: boto3 clients and DynamoDB
resources are created lazily on first use, never at import time.
"""
