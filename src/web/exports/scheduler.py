"""Еженедельный сбор и Excel. Запускается только отдельным профилем Compose."""
import signal
import subprocess
import sys
from datetime import datetime, timedelta
from threading import Event

from src.config import settings
from src.parser.report import REPORT_TIMEZONE


def next_run(now, weekday, hour, minute):
    local = now.astimezone(REPORT_TIMEZONE)
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    candidate += timedelta(days=(weekday - local.weekday()) % 7)
    if candidate <= local:
        candidate += timedelta(days=7)
    return candidate


def main():
    stopped = Event()
    process = None

    def stop(signum, frame):
        stopped.set()
        if process is not None and process.poll() is None:
            process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopped.is_set():
        day = next_run(datetime.now(REPORT_TIMEZONE), settings.ISUP_SCHEDULE_WEEKDAY,
                       settings.ISUP_SCHEDULE_HOUR, settings.ISUP_SCHEDULE_MINUTE)
        print(f"Следующий сбор: {day.isoformat()}", flush=True)
        while not stopped.is_set() and datetime.now(REPORT_TIMEZONE) < day:
            stopped.wait(min(30, max(0, (day - datetime.now(REPORT_TIMEZONE)).total_seconds())))
        if stopped.is_set():
            break
        command = [sys.executable, "-m", "src.parser.parser", "--http", "--save-db", "--archive", "all",
                   "--concurrency", str(settings.ISUP_SCHEDULE_CONCURRENCY), "--export-xlsx"]
        if settings.ISUP_SCHEDULE_UPLOAD:
            command.append("--upload-disk")
        process = subprocess.Popen(command)
        code = process.wait()
        process = None
        print(f"Плановый запуск завершён, код {code}. При ошибке повторите запуск/доставку вручную.", flush=True)


if __name__ == "__main__":
    main()
