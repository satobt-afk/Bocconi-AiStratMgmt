"""Shared pytest setup."""

import pytest

from backend import main


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Rate-limit counters live in memory for the whole run: start every test from zero."""
    main.limiter.reset()
    yield
    main.limiter.reset()
