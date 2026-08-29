"""Regression check for the 'async generator ignored GeneratorExit' bug.

Standalone script (deliberately NOT named test_* so pytest won't collect
it — it needs the args-bootstrap import order and mutates sys.argv):

    .venv/Scripts/python.exe test/general/sessionmanager_genexit_check.py

Simulates the download flow against the real sessionManager.requests_async
with a fake aiohttp layer:
  1. clean exit                 -> response released, sem balanced
  2. consumer error mid-stream  -> ORIGINAL exception propagates (not RuntimeError)
  3. request failure then success -> internal retry still works
  4. close() while suspended at the yield (what GC does) -> GeneratorExit honored
  5. cancellation during request -> propagates, not retried, sem balanced
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))


async def run_scenarios():
    # import through the app's bootstrap (args must parse first to break the
    # settings <-> console circular import)
    sys.argv = [sys.argv[0]]
    import ofscraper.main.open.load as _load  # noqa: F401

    import ofscraper.managers.sessionmanager.sessionmanager as sm

    class FakeResp:
        def __init__(self):
            self.ok = True
            self.status_code = 200
            self.released = False

        async def text_(self):
            return ""

        def raise_for_status(self):
            pass

        async def release(self):
            self.released = True

    # ---- 1: clean exit ----
    m = sm.sessionManager(sem_count=1)
    fake = FakeResp()

    async def f(method, url, **kw):
        return fake

    m._aio_funct = f
    async with m.requests_async(url="http://x") as r:
        pass
    assert fake.released, "response should be released on clean exit"
    assert m._sem._value == 1, f"sem unbalanced: {m._sem._value}"
    print("1 OK: clean exit -> released + sem balanced")

    # ---- 2: consumer raises mid-stream (chunk timeout) ----
    m2 = sm.sessionManager(sem_count=1)
    fake2 = FakeResp()

    async def f2(method, url, **kw):
        return fake2

    m2._aio_funct = f2

    class ChunkTimeout(Exception):
        pass

    try:
        async with m2.requests_async(url="http://x") as r:
            raise ChunkTimeout("cdn went silent")
    except ChunkTimeout:
        pass
    else:
        raise AssertionError("original exception was swallowed/replaced!")
    assert m2._sem._value == 1, f"sem unbalanced: {m2._sem._value}"
    assert fake2.released, "response not released after consumer error"
    print("2 OK: consumer exception propagates untouched, sem balanced, released")

    # ---- 3: request fails once, retry inside requests_async succeeds ----
    m3 = sm.sessionManager(sem_count=1, wait_min=0.01, wait_max=0.02)
    calls = {"n": 0}

    async def f3(method, url, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("conn reset")
        return FakeResp()

    m3._aio_funct = f3
    async with m3.requests_async(url="http://x") as r:
        pass
    assert calls["n"] == 2, f"expected 2 attempts, got {calls['n']}"
    assert m3._sem._value == 1, f"sem unbalanced: {m3._sem._value}"
    print("3 OK: internal request retry works, sem balanced")

    # ---- 4: aclose() while suspended at the yield (GC finalization path) ----
    m4 = sm.sessionManager(sem_count=1)
    fake4 = FakeResp()

    async def f4(method, url, **kw):
        return fake4

    m4._aio_funct = f4
    cm = m4.requests_async(url="http://x")
    await cm.__aenter__()
    try:
        await cm.gen.aclose()  # throws GeneratorExit at the yield, like the GC hook
    except RuntimeError as e:
        raise AssertionError(f"GeneratorExit not honored: {e}")
    assert m4._sem._value == 1, f"sem unbalanced: {m4._sem._value}"
    assert fake4.released, "response not released on close"
    print("4 OK: GeneratorExit honored on close, sem balanced, released")

    # ---- 5: cancellation during the request phase ----
    m5 = sm.sessionManager(sem_count=1, wait_min=0.01, wait_max=0.02)
    started = asyncio.Event()

    async def f5(method, url, **kw):
        started.set()
        await asyncio.sleep(30)

    m5._aio_funct = f5
    task = asyncio.create_task(m5.requests_async(url="http://x").__aenter__())
    await started.wait()
    task.cancel()
    try:
        await task
        raise AssertionError("CancelledError was swallowed")
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(0.05)
    assert m5._sem._value == 1, f"sem unbalanced after cancel: {m5._sem._value}"
    print("5 OK: cancellation propagates (not retried), sem balanced")

    print("ALL SCENARIOS PASSED")


if __name__ == "__main__":
    run = run_scenarios()
    asyncio.run(run)
