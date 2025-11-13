import logging, sys, os, ctypes
from functools import wraps
from typing import Callable

def _enable_vt():
    if os.name == "nt":
        try:
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if k32.GetConsoleMode(h, ctypes.byref(mode)):
                k32.SetConsoleMode(h, mode.value | 0x0004)
        except Exception:
            pass


class SoftColorFormatter(logging.Formatter):
    RESET = "\x1b[0m"
    BOLD  = "\x1b[1m"

    # --- Muted, darker colors (256-color codes) ---
    SOFT_BLUE   = "\x1b[38;5;67m"   # deep steel blue for DEBUG
    SOFT_GREEN  = "\x1b[38;5;71m"   # soft forest green for INFO
    SOFT_AMBER  = "\x1b[38;5;137m"  # amber-brown for WARNING
    SOFT_RED    = "\x1b[38;5;124m"  # brick red for ERROR
    SOFT_CRIT   = "\x1b[38;5;160m"  # deep crimson for CRITICAL
    GRAY        = "\x1b[38;5;244m"  # dim gray for timestamps etc.

    ICONS = {
        logging.DEBUG:    "·",
        logging.INFO:     "•",
        logging.WARNING:  "!",
        logging.ERROR:    "✖",
        logging.CRITICAL: "✖",
    }

    COLORS = {
        logging.DEBUG:    SOFT_BLUE,
        logging.INFO:     SOFT_GREEN,
        logging.WARNING:  SOFT_AMBER,
        logging.ERROR:    SOFT_RED,
        logging.CRITICAL: SOFT_CRIT,
    }

    def format(self, record: logging.LogRecord) -> str:
        icon = self.ICONS.get(record.levelno, "")
        color = self.COLORS.get(record.levelno, "")
        base = super().format(record)
        # make the prefix gray and the message colorized
        parts = base.split("|", 3)
        if len(parts) >= 4:
            prefix = "|".join(parts[:3])
            msg = parts[3]
            return f"{self.GRAY}{prefix}|{self.RESET}{color}{self.BOLD}{icon}{msg}{self.RESET}"
        return f"{color}{self.BOLD}{icon}{base}{self.RESET}"


def _base() -> logging.Logger:
    _enable_vt()
    lg = logging.getLogger("netdemo")
    if lg.handlers:
        return lg
    lg.setLevel(logging.DEBUG)
    h = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
    h.setFormatter(SoftColorFormatter(fmt))
    lg.addHandler(h)
    lg.propagate = False
    return lg


def get_logger(name: str) -> logging.Logger:
    return _base().getChild(name)


def log_call(level: int = logging.DEBUG) -> Callable:
    def deco(fn: Callable) -> Callable:
        lg = get_logger(f"{fn.__module__}.{fn.__qualname__}")
        @wraps(fn)
        def wrap(*a, **kw):
            lg.log(level, "START %s args=%r kwargs=%r", fn.__name__, a, kw)
            r = fn(*a, **kw)
            lg.log(level, "END   %s -> %r", fn.__name__, r)
            return r
        return wrap
    return deco
