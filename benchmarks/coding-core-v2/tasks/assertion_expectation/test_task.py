"""Fails against the buggy fixture; passes once totals() stops adding
one. Side-effect free, deterministic.
"""
from task import totals


def test_totals_sums_items():
    assert totals([1, 2, 3]) == 6
