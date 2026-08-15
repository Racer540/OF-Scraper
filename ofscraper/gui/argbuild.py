"""
Argument builder: turns GUI form state into the same args the CLI produces.

Parity by construction: instead of re-implementing defaults, callbacks and
cloup constraints, the GUI assembles an argv list and runs it through the real
CLI parser (`ofscraper/utils/args/parse/commands/main.py:program`), exactly
like `ofscraper.utils.args.main.parse_args` does -- just with our argv instead
of sys.argv.  The parsed params then flow through the normal
`settings.update_args` merge, so downstream code sees a fully-formed job.

Bad input surfaces as click.UsageError, which callers should catch and show
as a form error.
"""

import logging

import ofscraper.utils.args.parse.commands.db as db
import ofscraper.utils.args.parse.commands.main as main
import ofscraper.utils.args.parse.commands.manual as manual
import ofscraper.utils.args.parse.commands.message as message
import ofscraper.utils.args.parse.commands.metadata as metadata
import ofscraper.utils.args.parse.commands.paid as paid
import ofscraper.utils.args.parse.commands.post as post
import ofscraper.utils.args.parse.commands.story as story
import ofscraper.utils.settings as settings
from ofscraper.utils.args.main import AutoDotDict

log = logging.getLogger("shared")

_REGISTERED = False


def register_commands():
    """Attach subcommands to the main group (mirrors parse_args).

    Idempotent: the first lazy retriveArgs() in the import chain may already
    have run parse_args(), which registers the same commands -- cloup raises
    on duplicates, so swallow 'already exists'.
    """
    global _REGISTERED
    if _REGISTERED:
        return
    for cmd, name in [
        (manual.manual, "manual"),
        (message.message_check, "msg_check"),
        (story.story_check, "story_check"),
        (paid.paid_check, "paid_check"),
        (post.post_check, "post_check"),
        (metadata.metadata, "metadata"),
        (db.db, "db"),
    ]:
        try:
            main.program.add_command(cmd, name)
        except Exception:
            pass
    _REGISTERED = True


def build_job(argv: list) -> AutoDotDict:
    """Parse argv with the real CLI parser and install it as global settings.

    Returns the AutoDotDict now stored in the global args/settings.
    Raises click.UsageError (or similar) on invalid input.
    """
    register_commands()
    result = main.program(
        standalone_mode=False,
        prog_name="OF-Scraper",
        args=list(argv),
    )
    if result == 0:  # pragma: no cover - only for help/version in CLI mode
        raise ValueError("CLI parser requested exit; not supported in GUI mode")
    args, command = result
    args["command"] = command
    d = AutoDotDict(args)
    settings.update_args(d)
    log.debug(f"GUI built job from argv {argv} (command={command})")
    return d
