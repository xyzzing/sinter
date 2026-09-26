"""Fails against the buggy fixture; passes once get_setting defaults
missing keys. Kept side-effect free so the 8D sandbox can run it as-is.
"""
from task import get_setting


def test_missing_key_returns_none():
    assert get_setting("absent_key") is None


def test_known_key_returns_value():
    assert get_setting("retries") == 2
