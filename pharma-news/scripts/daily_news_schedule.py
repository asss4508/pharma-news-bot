"""Arm an early Actions runner for 06:13 KST instead of exiting before dawn.

No Telegram/network access: this module only gates and waits. The workflow's
shared concurrency group and checkout of current main protect the daily ledger.
Actions can still delay/drop every early trigger; this is not an uptime SLA.
"""

import argparse
from datetime import datetime, time, timedelta, timezone
import os
from pathlib import Path
import time as clock

KST = timezone(timedelta(hours=9))
SEND_TIME = time(6, 13)
MAX_WAIT = timedelta(hours=5, minutes=30)


def choose_target(now, last_sent, *, manual=False, force=False):
    """Return today's send time, or None when this execution should exit."""
    if now.tzinfo is None:
        raise ValueError("Timezone-aware time required")
    now = now.astimezone(KST)
    if last_sent.strip() == now.date().isoformat() and not (manual and force):
        return None
    if manual:
        return now  # Manual runs are immediate, but duplicate-safe by default.
    target = datetime.combine(now.date(), SEND_TIME, tzinfo=KST)
    if now < target - MAX_WAIT:
        return None  # Leave 25+ minutes for sending before the job timeout.
    return target  # Past target means catch up immediately, not tomorrow.


def wait_until(target, *, now_fn=None, sleep_fn=clock.sleep):
    if target.tzinfo is None:
        raise ValueError("Timezone-aware target required")
    target = target.astimezone(KST)
    now_fn = now_fn or (lambda: datetime.now(KST))
    print(f"발송 목표: {target.isoformat()}", flush=True)
    while True:
        now = now_fn().astimezone(KST)
        if now.date() != target.date():
            raise RuntimeError("발송 날짜가 바뀌었습니다. 새 예약 실행에서 다시 판단해야 합니다.")
        remaining = (target - now).total_seconds()
        if remaining <= 0:
            print(f"발송 시작: {now.isoformat()} (목표 대비 {max(0, -remaining):.1f}초)", flush=True)
            return
        if remaining > MAX_WAIT.total_seconds():
            raise RuntimeError("작업 시간 한도를 넘는 대기는 허용하지 않습니다.")
        sleep_fn(min(remaining, 60))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("gate", "wait"))
    parser.add_argument("--target")
    args = parser.parse_args()
    if args.mode == "wait":
        if not args.target:
            parser.error("wait requires --target")
        wait_until(datetime.fromisoformat(args.target))
        return

    ledger = Path("data/daily_news_last_sent.txt")
    last_sent = ledger.read_text(encoding="utf-8") if ledger.exists() else ""
    target = choose_target(
        datetime.now(KST), last_sent,
        manual=os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch",
        force=os.environ.get("FORCE_SEND", "").lower() == "true",
    )
    outputs = f"proceed={str(target is not None).lower()}\n"
    if target is not None:
        outputs += f"target={target.isoformat()}\nsend_date={target.date().isoformat()}\n"
    print(outputs, end="", flush=True)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(outputs)


if __name__ == "__main__":
    main()
