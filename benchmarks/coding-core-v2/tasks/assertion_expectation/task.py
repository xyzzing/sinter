"""coding-core-v1 / t3_assertion_expectation fixture (8C manifest
content).

Deliberate off-by-one: totals() returns one too many, so the assertion
never matches the expectation. The verified fix removes the +1. Safe,
offline, deterministic.
"""


def totals(items):
    return sum(items) + 1
