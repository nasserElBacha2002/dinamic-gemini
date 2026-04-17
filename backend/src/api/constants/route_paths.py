"""Stable v3 HTTP path prefixes for FastAPI ``APIRouter(prefix=...)``.

Must match mounted URLs exactly. Change only with coordinated contract tests.
Does not import routes or domain logic.
"""

API_V3_PREFIX = "/api/v3"

# Mounted router prefixes (each is a full prefix string for ``APIRouter``).
API_V3_INVENTORIES_ROUTER_PREFIX = f"{API_V3_PREFIX}/inventories"
API_V3_ANALYTICS_ROUTER_PREFIX = f"{API_V3_PREFIX}/analytics"
API_V3_REVIEW_QUEUE_ROUTER_PREFIX = f"{API_V3_PREFIX}/review-queue"
API_V3_ADMIN_ROUTER_PREFIX = f"{API_V3_PREFIX}/admin"

# Session auth routes (mounted separately from v3 business routers).
API_AUTH_ROUTER_PREFIX = "/auth"
