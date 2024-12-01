try:
    from langgraph_api.js.remote import (
        RemoteException,
        RemotePregel,
        js_healthcheck,
        run_js_process,
        run_remote_checkpointer,
        run_remote_store,
        wait_until_js_ready,
    )
except ImportError:

    class RemotePregel:
        pass

    RemoteException = RemotePregel

    async def js_healthcheck() -> None:
        pass

    async def run_js_process(paths_str: str, watch: bool = False):
        pass

    async def run_remote_checkpointer() -> None:
        pass

    async def run_remote_store() -> None:
        pass

    async def wait_until_js_ready() -> None:
        pass


__all__ = [
    "RemotePregel",
    "RemoteException",
    "js_healthcheck",
    "run_js_process",
    "run_remote_checkpointer",
    "run_remote_store",
    "wait_until_js_ready",
]
