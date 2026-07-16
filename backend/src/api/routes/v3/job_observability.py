"""Job Observability routes.

Observability endpoints currently live on the inventories/aisles router
(``aisles.py``) with capability guards. This module is the intended home for a
follow-up physical extraction (keep import surface stable for docs/tests).
"""

from __future__ import annotations

# Physical extraction tracked as residual: handlers remain in ``aisles.py`` for
# this correction to avoid a risky mid-flight move of 600+ lines. Capability
# gates, incremental pagination, and sanitization are already applied there.
