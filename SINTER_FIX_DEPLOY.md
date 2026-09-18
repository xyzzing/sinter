# Sinter fix-deployment runbook (for dsh to execute)

Execute these steps IN ORDER in `~/projects/sinter`. Every edit has a
verification anchor: locate the exact existing pattern first; if it does
not match, STOP that step and report the actual file content instead of
inventing a patch. Do not refactor anything not listed here.

Out of scope (needs design decisions, do NOT touch):
- stale-lock PID reaping in lock.py
- the port TOCTOU race in supervisor.py
- any dsh config, MCP, or profile changes

---

## Step 0 — Preflight (fail closed)

```bash
cd ~/projects/sinter
git status --short
```

- If the tree is dirty: `git add -A && git commit -m "wip: pre-fix snapshot"` first.
- Confirm test runner: `python -m pytest --version`
- Record baseline: `python -m pytest tests/ -q 2>&1 | tail -5` and note pass/fail counts.

## Step 1 — Fix the /proc starttime off-by-one (src/sinter/supervisor.py)

Verify current state:

```bash
grep -n "rfind" src/sinter/supervisor.py
grep -n "fields\[2[0-9]\]" src/sinter/supervisor.py
```

Kernel fact (do not re-derive): in /proc/[pid]/stat, starttime is field 22.
After stripping pid (field 1) and comm (field 2), starttime is index 19 of
the remaining fields.

Apply ONE of:

- If an inline parse exists after `rfind(")")` using `fields[20]`:
  extract it into a module-level function and correct the index:

```python
def _parse_proc_start_time(stat_content: str) -> int:
    """starttime is stat field 22 -> index 19 after pid and comm are stripped."""
    idx = stat_content.rfind(")")
    fields = stat_content[idx + 1:].split()
    return int(fields[19])
```

  Replace the inline logic's call site to use the new function.

- If `_parse_proc_start_time` already exists with `fields[20]`: change 20 -> 19.
- If it already says `fields[19]`: skip, already fixed.

Verify: `grep -n "fields\[19\]" src/sinter/supervisor.py` returns a hit, and
`grep -n "fields\[20\]" src/sinter/supervisor.py` returns nothing for the
starttime parse.

## Step 2 — Replace the misleading procstat test (tests/)

Locate the stale test (exported names had suffixes; find the real one):

```bash
ls tests/ | grep -i procstat
grep -ln "def parse_start_time" tests/
```

The stale test redefines `parse_start_time` inline and asserts index 20 —
it tests a copy of buggy code, not production. Replace its entire content
with a version that IMPORTS the production parser. Use exactly this file:

```python
"""Fixed tests for /proc/[pid]/stat starttime parsing."""

from __future__ import annotations

import os
import unittest

from sinter.supervisor import _parse_proc_start_time


def make_stat(comm: str, starttime: int) -> str:
    # see Step 1 for kernel field mapping; starttime must sit at index 19
    tail = " ".join([
        "S", "1", "100", "100", "0", "-1",
        "4194304", "10", "0", "1", "0",
        "5", "3", "0", "0", "20", "0", "1",
        "0",                    # itrealvalue (index 18)
        str(starttime),         # starttime   (index 19)
        "1234567", "888",       # vsize, rss
    ])
    return f"4242 ({comm}) {tail}"


class TestParseProcStartTime(unittest.TestCase):

    def test_normal_comm(self):
        self.assertEqual(_parse_proc_start_time(make_stat("llama-server", 987654321)), 987654321)

    def test_spaces_in_comm(self):
        self.assertEqual(_parse_proc_start_time(make_stat("my proc name", 555555)), 555555)

    def test_parens_in_comm(self):
        self.assertEqual(_parse_proc_start_time(make_stat("proc(name)here", 777777)), 777777)

    def test_off_by_one_guard(self):
        # sentinel distinct from neighbours so a +/-1 index slip fails loudly
        self.assertEqual(_parse_proc_start_time(make_stat("x", 314159265)), 314159265)

    def test_matches_live_process(self):
        with open(f"/proc/{os.getpid()}/stat") as f:
            content = f.read()
        fields_after_comm = content[content.rfind(")") + 1:].split()
        self.assertEqual(_parse_proc_start_time(content), int(fields_after_comm[19]))


if __name__ == "__main__":
    unittest.main()
```

## Step 3 — Orphan-guard the acceptance journey (tests/test_acceptance.py)

Verify:

```bash
grep -n "def test_full_client_journey" tests/test_acceptance.py
grep -n "sup.stop" tests/test_acceptance.py
```

In `test_full_client_journey`, wrap everything after
`instance = sup.launch(...)` in `try:` and add:

```python
    finally:
        try:
            sup.stop(timeout=10.0)
        except Exception:
            pass
```

Purpose: a failed assertion must never leave a real 27B llama-server
holding the GPU. Keep the existing assertions and step order unchanged.

## Step 4 — Startup timeout per PRD (src/sinter/supervisor.py)

Verify:

```bash
grep -n "timeout" src/sinter/supervisor.py | grep -i "30\|launch"
```

If `launch(...)` has a default of `timeout: float = 30.0`, change it to
`180.0` (PRD spec; IQ4_XS 27B cold load exceeds 30 s). If the default
already reads 180.0 or the parameter moved into ProfileSpec, STOP and
report the actual signature instead of guessing.

## Step 5 — Run the suite

```bash
python -m pytest tests/ -q
```

Expected: all unit tests pass. The acceptance journey test may SKIP
(binary absent) — that is fine. If any test fails, report the failure
output verbatim and stop; do not "fix" tests to make them pass.

## Step 6 — Commit

```bash
git add -A
git commit -m "fix: procstat starttime index, acceptance finally-guard, 180s launch timeout; replace inline-parser test"
git log --oneline -1
```

## Report back

Print: baseline pytest summary vs final pytest summary, the diff stat
(`git show --stat HEAD`), and any steps that were skipped or stopped.
