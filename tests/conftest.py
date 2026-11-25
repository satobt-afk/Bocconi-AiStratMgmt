"""Shared pytest setup."""

import pytest

from backend import main


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Rate-limit counters live in memory for the whole run: start every test from zero."""
    main.limiter.reset()
    yield
    main.limiter.reset()


@pytest.fixture(autouse=True)
def never_touch_the_real_database(monkeypatch, tmp_path):
    """Any test that opens the default database gets a throwaway file instead of data/budget.db."""
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "test-budget.db"))
