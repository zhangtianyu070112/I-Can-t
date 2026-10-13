from __future__ import annotations

import contextvars
import logging
import atexit
from datetime import datetime
from pathlib import Path
import warnings
from typing import Any


request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")
        return True


class DailyFileHandler(logging.Handler):
    def __init__(self, dir_path: Path, encoding: str = "utf-8") -> None:
        super().__init__()
        self._dir_path = dir_path
        self._encoding = encoding
        self._date: str | None = None
        self._fp = None

    def _ensure_open(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        if self._fp and self._date == today:
            return
        if self._fp:
            try:
                self._fp.close()
            except Exception:
                pass
            self._fp = None
        self._dir_path.mkdir(parents=True, exist_ok=True)
        path = self._dir_path / f"{today}.log"
        self._fp = open(path, "a", encoding=self._encoding)
        self._date = today

    def emit(self, record: logging.LogRecord) -> None:
        self._ensure_open()
        msg = self.format(record)
        try:
            self._fp.write(msg + "\n")
            self._fp.flush()
        except Exception:
            pass

    def close(self) -> None:
        try:
            if self._fp:
                self._fp.close()
        finally:
            self._fp = None
            super().close()


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    lvl = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(lvl)

    handler = logging.StreamHandler()
    handler.setLevel(lvl)
    handler.addFilter(RequestIdFilter())
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s rid=%(request_id)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)

    repo_root = Path(__file__).resolve().parents[3]
    log_dir = repo_root / "log"
    file_handler = DailyFileHandler(log_dir)
    file_handler.setLevel(lvl)
    file_handler.addFilter(RequestIdFilter())
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    atexit.register(file_handler.close)

    for name in [
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
        "httpx",
    ]:
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True

    warnings.simplefilter("default")
    logging.captureWarnings(True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
