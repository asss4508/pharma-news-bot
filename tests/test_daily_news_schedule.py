import contextlib
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "pharma-news/scripts/daily_news_schedule.py"
spec = importlib.util.spec_from_file_location("daily_news_schedule", SCRIPT)
schedule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schedule)


def at(hour, minute=0, second=0, day=9):
    return datetime(2026, 9, day, hour, minute, second, tzinfo=schedule.KST)


class DailyNewsScheduleTests(unittest.TestCase):
    def test_actual_0554_execution_arms_for_0613(self):
        self.assertEqual(schedule.choose_target(at(5, 54), "2026-09-08"), at(6, 13))

    def test_earliest_wakeup_respects_runner_limit(self):
        self.assertIsNone(schedule.choose_target(at(0, 42, 59), ""))
        target = schedule.choose_target(at(0, 43), "")
        self.assertEqual(target - at(0, 43), timedelta(hours=5, minutes=30))

    def test_exact_time_and_late_execution_use_today(self):
        for now in (at(6, 13), at(8, 15), at(23, 59)):
            with self.subTest(now=now):
                self.assertEqual(schedule.choose_target(now, ""), at(6, 13))

    def test_duplicate_and_normal_manual_run_skip(self):
        for manual in (False, True):
            self.assertIsNone(schedule.choose_target(at(8), "2026-09-09\n", manual=manual))

    def test_force_resend_is_only_for_explicit_manual_run(self):
        self.assertEqual(schedule.choose_target(at(8), "2026-09-09", manual=True, force=True), at(8))
        self.assertIsNone(schedule.choose_target(at(8), "2026-09-09", force=True))

    def test_unsent_manual_run_is_immediate(self):
        self.assertEqual(schedule.choose_target(at(0, 10), "", manual=True), at(0, 10))

    def test_utc_input_uses_korean_calendar_date(self):
        now = at(5, 54).astimezone(timezone.utc)
        self.assertEqual(schedule.choose_target(now, "2026-09-08"), at(6, 13))
        self.assertIsNone(schedule.choose_target(now, "2026-09-09"))

    def test_new_day_resets_daily_gate(self):
        self.assertEqual(schedule.choose_target(at(1, day=10), "2026-09-09"), at(6, 13, day=10))

    def test_wait_absorbs_delay_without_new_scheduler_event(self):
        for start in (at(0, 43), at(5, 54), at(6, 12, 59)):
            with self.subTest(start=start):
                current = [start]
                sleeps = []

                def advance(seconds):
                    sleeps.append(seconds)
                    current[0] += timedelta(seconds=seconds)

                with contextlib.redirect_stdout(io.StringIO()):
                    schedule.wait_until(at(6, 13), now_fn=lambda: current[0], sleep_fn=advance)
                self.assertEqual(current[0], at(6, 13))
                self.assertTrue(all(0 < seconds <= 60 for seconds in sleeps))

    def test_late_runner_sends_without_waiting(self):
        with contextlib.redirect_stdout(io.StringIO()):
            schedule.wait_until(at(6, 13), now_fn=lambda: at(8, 15),
                                sleep_fn=lambda _: self.fail("Late execution must not sleep"))

    def test_stale_date_and_oversized_wait_fail_closed(self):
        for now in (at(0, day=10), at(0, 42)):
            with self.subTest(now=now), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    schedule.wait_until(at(6, 13), now_fn=lambda: now)

    def test_naive_time_is_rejected(self):
        with self.assertRaises(ValueError):
            schedule.choose_target(datetime(2026, 9, 9), "")
        with self.assertRaises(ValueError):
            schedule.wait_until(datetime(2026, 9, 9))

    def test_cli_output_and_duplicate_gate_without_telegram_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "outputs.txt"
            env = {"PATH": os.environ["PATH"], "GITHUB_OUTPUT": str(output),
                   "GITHUB_EVENT_NAME": "workflow_dispatch", "FORCE_SEND": "false"}
            subprocess.run([sys.executable, str(SCRIPT), "gate"], cwd=root, env=env,
                           check=True, capture_output=True, text=True)
            values = dict(line.split("=", 1) for line in output.read_text().splitlines())
            self.assertEqual(values["proceed"], "true")
            self.assertTrue(values["target"].endswith("+09:00"))
            (root / "data").mkdir()
            (root / "data/daily_news_last_sent.txt").write_text(values["send_date"] + "\n")
            output.write_text("")
            subprocess.run([sys.executable, str(SCRIPT), "gate"], cwd=root, env=env,
                           check=True, capture_output=True, text=True)
            self.assertEqual(output.read_text(), "proceed=false\n")


if __name__ == "__main__":
    unittest.main()
