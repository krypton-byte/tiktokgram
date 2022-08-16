import asyncio
from threading import Thread


async def coro():
    print("in coro")
    return 42


loop = asyncio.new_event_loop()
thread = Thread(target=loop.run_forever)
thread.start()

fut = asyncio.run_coroutine_threadsafe(coro(), loop)

print(fut.result())

loop.call_soon_threadsafe(loop.stop)

thread.join()