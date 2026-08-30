import logging
import time
import traceback

import httpx

import ofscraper.managers.sessionmanager.sessionmanager as sessionManager
import ofscraper.utils.of_env.of_env as of_env
import ofscraper.utils.settings as settings

CDM_HELP = (
    "check your cdm settings: "
    "https://of-scraper.gitbook.io/of-scraper/cdm-options"
)


def check_cdm():
    """Health-check the CDM key service.

    All messages go through the 'shared' logger (not console.print) so they
    reach the console, the log file, AND the GUI log pane -- in the windowed
    exe, console.print disappears into devnull.
    """
    log = logging.getLogger("shared")

    keymode = settings.get_settings().key_mode
    log.info(f"Key Mode: {keymode}")
    if keymode == "manual":
        log.warning(f"manual key mode: verify your device settings — {CDM_HELP}")
        return True
    elif keymode == "cdrm":
        url = of_env.getattr("CDRM")
    try:
        with sessionManager.sessionManager(
            total_timeout=of_env.getattr("CDM_TEST_TIMEOUT"),
            retries=of_env.getattr("CDM_TEST_NUM_TRIES"),
            wait_min=of_env.getattr("CDM_MIN_WAIT"),
            wait_max=of_env.getattr("CDM_MAX_WAIT"),
        ) as c:
            # The CDRM API is POST-only: a plain GET 404s on a perfectly
            # healthy service (self-hosted containers answer wrong-method
            # requests with a 404 page). Probe with a dummy POST instead --
            # any 2xx response proves the endpoint exists and answers.
            with c.requests(
                url=url, headers={}, method="post", json={}
            ) as r:
                if 200 <= r.status < 300:
                    log.info(f"CDM key service reachable at {url}")
                    return True
                else:
                    log.warning(
                        f"CDM key service returned HTTP {r.status} from {url} "
                        f"— DRM (protected) downloads will fail until it "
                        f"answers; {CDM_HELP}"
                    )
                    log.debug(f"cdm body: {r.text_()}")
                    time.sleep(3.5)
                    return False
    except httpx.TimeoutException:
        log.warning(
            f"CDM key service timed out and seems down ({url}) — DRM "
            f"(protected) downloads will fail; {CDM_HELP}"
        )
        log.debug(traceback.format_exc())
        time.sleep(3.5)

    except Exception as E:
        log.warning(
            f"CDM key service has an issue: {E} ({url}) — DRM (protected) "
            f"downloads will fail; {CDM_HELP}"
        )
        log.debug(traceback.format_exc())
        time.sleep(3.5)
    return False
