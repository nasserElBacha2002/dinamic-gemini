"""
Stable provider/model strings for application-layer tests that only assert persistence / round-trip.

Use registered catalog keys so later flows (e.g. process-aisle) stay valid without tying tests to Gemini.
"""

from __future__ import annotations

# Stub operational resolver / job snapshots — OpenAI is used to avoid an implicit “Gemini is the test default”.
STUB_PRIMARY_PROVIDER = "openai"
STUB_PRIMARY_MODEL = "gpt-4o"
