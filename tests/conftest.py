"""Test defaults.

Production defaults to AUTH_REQUIRED=1 (see server/auth.py). The test suite
doesn't have Supabase accounts, so disable the bearer check by default; the
tenant-auth tests flip it back on explicitly. ``setdefault`` is important:
a developer's shell env still wins if they deliberately set it.
"""
import os

os.environ.setdefault("AUTH_REQUIRED", "0")
