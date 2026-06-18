import logging
import json
import os
from datetime import datetime, timezone
from src.core.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "data") and record.data:
            log_entry["data"] = record.data
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = f"{color}[{ts}] [{record.levelname}] [{record.name}]{self.RESET}"
        msg = f"{prefix} {record.getMessage()}"
        if record.exc_info and record.exc_info[0]:
            msg += "\n" + self.formatException(record.exc_info)
        return msg


_root_logger = logging.getLogger("rebugger")
_root_logger.setLevel(logging.DEBUG)
_root_logger.propagate = False

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(ConsoleFormatter())
_root_logger.addHandler(_console_handler)

_session_handlers: dict = {}


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"rebugger.{name}")


def setup_session_logger(thread_id: str) -> None:
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    log_path = os.path.join(settings.LOG_DIR, f"{thread_id}.jsonl")
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(JsonFormatter())
    _root_logger.addHandler(handler)
    _session_handlers[thread_id] = handler


def teardown_session_logger(thread_id: str) -> None:
    handler = _session_handlers.pop(thread_id, None)
    if handler:
        _root_logger.removeHandler(handler)
        handler.close()
