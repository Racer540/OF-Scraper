"""
Job runner: executes OF-Scraper jobs on a dedicated worker thread.

Design notes (see plan):
- NiceGUI owns the main thread + its uvicorn loop; UI stays responsive.
- Each job runs on its own daemon thread.  The pipeline's `@run`-decorated
  coroutines self-heal in non-main threads (ofscraper/utils/context/
  run_async.py catches the get_event_loop RuntimeError and creates a fresh
  loop), so `Manager.pick()` can simply be called synchronously here.
- `Manager.start()` is deliberately NOT used: it sleeps 3 s and calls
  exit_manager.shutdown() (managers/manager.py:48-53), which closes the
  thread executor and cache that later jobs expect to re-create lazily.
  shutdown() runs once at app exit instead.
- The codebase assumes a single job at a time; the job lock in GuiState is
  the guard every Run button must pass through.
"""

import logging
import threading
import traceback

import ofscraper.gui.argbuild as argbuild
from ofscraper.gui.errors import GuiAuthRequired, GuiModeError, GuiPromptError
from ofscraper.gui.state import get_state

log = logging.getLogger("shared")


class JobRunner:
    """Starts jobs and reports their outcome through GuiState."""

    def start(self, argv: list, description: str = "") -> bool:
        """Launch a job.  Returns False if another job is already running."""
        state = get_state()
        if not state.begin_job(description):
            log.warning("Refused to start job: another job is active")
            return False
        thread = threading.Thread(
            target=self._worker,
            args=(list(argv), description),
            name="ofscraper-gui-job",
            daemon=True,
        )
        thread.start()
        return True

    # ------------------------------------------------------------------ #
    def _worker(self, argv: list, description: str):
        state = get_state()
        state.log_buffer.clear()
        try:
            argbuild.build_job(argv)
            manager = self._get_manager()
            # Clear leftover selection queues so the 'reset username' prompt
            # can never fire between jobs (managers/model.py:93-105).
            manager.current_model_manager.clear_all_queue()
            log.info(f"Starting job: {description or ' '.join(argv)}")
            manager.pick()
            state.finish_job(result="Job finished")
        except KeyboardInterrupt:
            log.warning("Job cancelled by user")
            state.finish_job(result="Job cancelled")
        except GuiAuthRequired:
            log.warning("Job stopped: authentication required")
            state.finish_job(
                result="Authentication required — open the Auth screen and log in"
            )
        except GuiPromptError as E:
            log.error(str(E))
            state.finish_job(result=str(E))
        except GuiModeError as E:  # future GUI control-flow errors
            state.finish_job(result=str(E))
        except Exception as E:
            log.debug(traceback.format_exc())
            log.error(f"Job failed: {E}")
            state.finish_job(error=f"{type(E).__name__}: {E}")
        finally:
            # belt-and-suspenders: SystemExit/GeneratorExit skip the except
            # clauses above; never leave the job lock held.
            if state.job_running:
                state.finish_job(error="Job thread exited unexpectedly")

    def _get_manager(self):
        import ofscraper.managers.manager as manager_module

        if not isinstance(manager_module.Manager, manager_module.mainManager):
            manager_module.Manager = manager_module.mainManager()
        return manager_module.Manager


runner = JobRunner()
