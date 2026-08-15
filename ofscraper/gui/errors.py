"""
Exceptions used to divert console-only code paths when running in GUI mode.

The core OF-Scraper pipeline still contains console prompts (InquirerPy) and
other terminal-only interactions.  The GUI installs monkeypatches that turn
those interactions into these exceptions so a worker thread can never hang
waiting for terminal input that will never come.
"""


class GuiModeError(Exception):
    """Base class for all GUI-mode control-flow exceptions."""


class GuiPromptError(GuiModeError):
    """A console prompt was reached that the GUI did not pre-answer.

    The GUI always builds a full argument set so prompts are skipped; if one
    fires anyway this exception aborts the job with a descriptive message
    instead of blocking the worker thread on terminal input.
    """

    def __init__(self, prompt_name: str):
        self.prompt_name = prompt_name
        super().__init__(
            f"Console prompt '{prompt_name}' was reached during a GUI job; "
            "the GUI did not provide an equivalent answer. "
            "Please report this so the screen can cover it."
        )


class GuiAuthRequired(GuiModeError):
    """Auth is missing/invalid and the console auth flow cannot run in the GUI.

    The runner maps this to a user-facing 'open the Auth screen' message.
    """
