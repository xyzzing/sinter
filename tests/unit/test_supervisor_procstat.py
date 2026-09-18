"""Edge-case tests for /proc/[pid]/stat parsing with spaces in comm field."""

from __future__ import annotations

import unittest


def parse_start_time(stat_content: str) -> int:
    """Extract start_time from /proc/[pid]/stat content."""
    idx = stat_content.rfind(")")
    after_comm = stat_content[idx + 1:].strip()
    fields = after_comm.split()
    # after_comm fields: state(0), ppid(1), pgrp(2), session(3), tty_nr(4),
    # tpgid(5), flags(6), minflt(7), cminflt(8), majflt(9), cmajflt(10),
    # utime(11), stime(12), cutime(13), cstime(14), priority(15), nice(16),
    # num_threads(17), itrealvalue(18), starttime(19)
    return int(fields[20])


class TestProcStatParsing(unittest.TestCase):
    """Test that start_time extraction handles comm fields with spaces."""

    def test_parse_proc_stat_with_spaces_in_comm(self):
        """Process names with spaces should not break start_time parsing."""
        # 20 fields after comm: state ppid pgrp session tty tpgid flags minflt
        # cminflt majflt cmajflt utime stime cutime cstime priority nice
        # num_threads itrealvalue starttime
        stat_content = (
            "12345 (my proc name) S 1 12345 12345 4 12345 "
            "0 0 0 0 0 0 100 200 300 400 20 0 1 0 "
            "987654321 999 888"
        )
        start_time = parse_start_time(stat_content)
        self.assertEqual(start_time, 987654321)

    def test_parse_proc_stat_normal(self):
        """Normal process name without spaces."""
        stat_content = (
            "12345 (llama-server) S 1 12345 12345 4 12345 "
            "0 0 0 0 0 0 100 200 300 400 20 0 1 0 "
            "555555 999 888"
        )
        start_time = parse_start_time(stat_content)
        self.assertEqual(start_time, 555555)

    def test_parse_proc_stat_parens_in_name(self):
        """Process name with parentheses."""
        stat_content = (
            "12345 (proc(name)here) S 1 12345 12345 4 12345 "
            "0 0 0 0 0 0 100 200 300 400 20 0 1 0 "
            "777777 999 888"
        )
        start_time = parse_start_time(stat_content)
        self.assertEqual(start_time, 777777)


if __name__ == "__main__":
    unittest.main()
