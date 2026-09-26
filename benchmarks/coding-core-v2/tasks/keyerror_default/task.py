"""coding-core-v1 / t3_keyerror_default fixture (8C manifest content).

Deliberate bug: reading a settings key without a default raises
KeyError, and retrying the same lookup loops forever - the canonical
stuck loop family. The verified fix is a .get() default. Safe, offline,
deterministic; the 8D runner executes it inside a fresh sandbox.
"""
SETTINGS = {"retries": 2}


def get_setting(key, settings=None):
    settings = settings or SETTINGS
    return settings[key]
