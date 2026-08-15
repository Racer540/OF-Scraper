"""
Progress bridge: snapshots the Rich progress singletons for GUI rendering.

All progress state in OF-Scraper lives in Rich `Progress` objects created once
in `ofscraper/utils/live/progress.py` and exposed as facades in
`ofscraper/utils/live/updater.py` (activity, api, userlist, metadata,
download, like).  Rich `Progress.tasks` is readable programmatically without a
terminal, so the GUI just polls a snapshot at ~2 Hz instead of rendering Live
output.

Descriptions use Rich markup (e.g. "[bold red]Downloading[/]"); `plain()`
converts them to display text using Rich's own parser.
"""

from dataclasses import dataclass, field

from rich.text import Text


@dataclass
class TaskSnapshot:
    id: object = None
    description: str = ""
    completed: float = 0
    total: float | None = None
    visible: bool = True
    fields: dict = field(default_factory=dict)

    @property
    def fraction(self) -> float:
        if not self.total:
            return 0.0
        return min(1.0, (self.completed or 0) / self.total)


def plain(text) -> str:
    """Strip Rich markup from a description string."""
    if text is None:
        return ""
    try:
        return Text.from_markup(str(text)).plain.strip()
    except Exception:
        return str(text).strip()


def _snap_tasks(progress) -> list:
    if progress is None:
        return []
    out = []
    try:
        for task in progress.tasks:
            fields = {k: v for k, v in getattr(task, "fields", {}).items()}
            out.append(
                TaskSnapshot(
                    id=task.id,
                    description=plain(task.description),
                    completed=task.completed or 0,
                    total=task.total,
                    visible=task.visible,
                    fields=fields,
                )
            )
    except Exception:
        pass
    return out


def snapshot() -> dict:
    """Return a plain-data snapshot of every progress facade."""
    import ofscraper.utils.live.updater as updater

    return {
        "activity_desc": _snap_tasks(updater.activity.desc),
        "activity_counter": _snap_tasks(updater.activity.counter),
        "api": {
            "job": _snap_tasks(updater.api.job),
            "overall": _snap_tasks(updater.api.overall),
        },
        "userlist": {
            "job": _snap_tasks(updater.userlist.job),
            "overall": _snap_tasks(updater.userlist.overall),
        },
        "metadata": {
            "overall": _snap_tasks(updater.metadata.overall),
        },
        "download": {
            "job": _snap_tasks(updater.download.job),
            "overall": _snap_tasks(updater.download.overall),
        },
        "like": {
            "overall": _snap_tasks(updater.like.overall),
        },
    }
