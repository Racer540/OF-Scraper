"""
Log bridge: captures formatted log records for the GUI log pane.

The codebase already has a widget seam for streaming logs --
`ofscraper.utils.logs.logger.add_widget(widget)` sets a `widget` attribute on
every TextHandler attached to the "shared" logger, and TextHandler.emit then
calls `widget.write(line)` (see ofscraper/utils/logs/classes/handlers/text.py).
That seam was built for the Textual log page; LogBuffer is the GUI-side
implementation of the same interface.

Worker threads append; a NiceGUI timer drains.  No UI objects are touched
here, so it is safe to call `write` from any thread.
"""

import threading
from collections import deque


class LogBuffer:
    """Thread-safe bounded buffer with the `write(line)` widget interface."""

    def __init__(self, maxlen: int = 5000):
        self._lines: deque[str] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def write(self, line) -> None:
        text = str(line).rstrip("\n")
        if not text:
            return
        with self._lock:
            self._lines.append(text)

    def drain(self) -> list:
        """Atomically remove and return all buffered lines."""
        with self._lock:
            out = list(self._lines)
            self._lines.clear()
        return out

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._lines)
