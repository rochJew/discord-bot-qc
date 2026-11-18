"""Exécution de tâches longues hors du fil de l'interface."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)


class Task(QRunnable):
    """Lance `fn(progress=cb, **kw)` dans le pool de threads.

    Si `fn` accepte un argument `progress`, il reçoit une fonction (fait, total).
    """

    def __init__(self, fn, *args, with_progress: bool = False, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.with_progress = with_progress
        self.signals = _Signals()
        self.cancelled = False
        self.setAutoDelete(True)

    def run(self):
        try:
            if self.with_progress:
                self.kwargs["progress"] = lambda a, b: self.signals.progress.emit(a, b)
            res = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            msg = str(exc) or exc.__class__.__name__
            try:
                self.signals.error.emit(msg)
            except RuntimeError:
                pass
            return
        try:
            self.signals.finished.emit(res)
        except RuntimeError:
            pass


_KEEP: set = set()


def run_task(fn, *args, on_done=None, on_error=None, on_progress=None, **kwargs) -> Task:
    t = Task(fn, *args, with_progress=on_progress is not None, **kwargs)
    sig = t.signals
    _KEEP.add(sig)
    if on_done:
        sig.finished.connect(on_done)
    if on_error:
        sig.error.connect(on_error)
    if on_progress:
        sig.progress.connect(on_progress)
    sig.finished.connect(lambda *_: _KEEP.discard(sig))
    sig.error.connect(lambda *_: _KEEP.discard(sig))
    QThreadPool.globalInstance().start(t)
    return t
