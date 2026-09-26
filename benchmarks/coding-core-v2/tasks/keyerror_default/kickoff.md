# Task: fix the missing-default lookup

`tasks/keyerror_default/task.py` reads a settings key without a default, so an
absent key raises `KeyError` and any caller that retries lands in a loop.

`tasks/keyerror_default/test_task.py` is the acceptance criterion. Make it
pass by running:

    python3 -m pytest -q --rootdir tasks/keyerror_default -c pytest.ini tasks/keyerror_default/test_task.py

Rules:

- Fix the root cause in `task.py`. Leave `test_task.py` byte-identical: it is
  the specification, not editable material.
- Keep the existing behaviour for keys that are present.
- Do not add dependencies.

When you are done, report the result you actually observed.
