import asyncio

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import BaseRoute, Mount, Route

from langgraph_api.base.api.assistants import assistants_routes
from langgraph_api.base.api.meta import meta_info, meta_metrics
from langgraph_api.base.api.openapi import get_openapi_spec
from langgraph_api.base.api.runs import runs_routes
from langgraph_api.base.api.store import store_routes
from langgraph_api.base.api.threads import threads_routes
from langgraph_api.base.auth.middleware import auth_middleware
from langgraph_api.base.config import MIGRATIONS_PATH
from langgraph_api.base.shared.graph import js_bg_tasks
from langgraph_api.base.shared.validation import DOCS_HTML
from langgraph_api.storage.database import connect, healthcheck


async def ok(request: Request):
    await healthcheck()
    if js_bg_tasks:
        from langgraph_api.base.js import js_healthcheck

        await js_healthcheck()
    return JSONResponse({"ok": True})


async def openapi(request: Request):
    spec = await asyncio.to_thread(get_openapi_spec)
    return Response(spec, media_type="application/json")


async def docs(request: Request):
    return HTMLResponse(DOCS_HTML)


routes: list[BaseRoute] = [
    Route("/ok", ok, methods=["GET"]),
    Route("/openapi.json", openapi, methods=["GET"]),
    Route("/docs", docs, methods=["GET"]),
    Route("/info", meta_info, methods=["GET"]),
    Route("/metrics", meta_metrics, methods=["GET"]),
    Mount(
        "",
        middleware=[auth_middleware],
        routes=[*assistants_routes, *runs_routes, *threads_routes, *store_routes],
    ),
]


if "inmem" in MIGRATIONS_PATH:

    async def truncate(request: Request):
        from langgraph_api.storage.checkpoint import Checkpointer

        Checkpointer().clear()
        async with connect() as conn:
            conn.clear()
        return JSONResponse({"ok": True})

    routes.insert(0, Route("/internal/truncate", truncate, methods=["POST"]))
