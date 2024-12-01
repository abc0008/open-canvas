import asyncio
import glob
import importlib.util
import inspect
import json
import os
import sys
from collections.abc import Callable
from itertools import filterfalse
from random import choice
from typing import NamedTuple
from uuid import UUID, uuid5

import structlog
from langchain_core.runnables.config import run_in_executor
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import Graph
from langgraph.pregel import Pregel
from langgraph.store.base import BaseStore
from starlette.exceptions import HTTPException

from langgraph_api.base.js import RemotePregel
from langgraph_api.base.shared.schema import Config

logger = structlog.stdlib.get_logger(__name__)

GraphFactoryFromConfig = Callable[[Config], Pregel | Graph]
GraphFactory = Callable[[], Pregel | Graph]
GraphValue = Pregel | GraphFactory


GRAPHS: dict[str, Pregel | GraphFactoryFromConfig | GraphFactory] = {}
NAMESPACE_GRAPH = UUID("6ba7b821-9dad-11d1-80b4-00c04fd430c8")
FACTORY_ACCEPTS_CONFIG: dict[str, bool] = {}


async def register_graph(graph_id: str, graph: GraphValue, config: dict | None) -> None:
    """Register a graph."""
    from langgraph_api.storage.database import connect
    from langgraph_api.storage.ops import Assistants

    await logger.ainfo(f"Registering graph with id '{graph_id}'", graph_id=graph_id)
    GRAPHS[graph_id] = graph
    if callable(graph):
        FACTORY_ACCEPTS_CONFIG[graph_id] = len(inspect.signature(graph).parameters) > 0
    async with connect() as conn:
        await Assistants.put(
            conn,
            str(uuid5(NAMESPACE_GRAPH, graph_id)),
            graph_id=graph_id,
            metadata={"created_by": "system"},
            config=config or {},
            if_exists="do_nothing",
            name=graph_id,
        )


def get_graph(
    graph_id: str,
    config: Config,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
) -> Pregel:
    """Return the runnable."""
    assert_graph_exists(graph_id)
    value = GRAPHS[graph_id]
    if graph_id in FACTORY_ACCEPTS_CONFIG:
        value = value(config) if FACTORY_ACCEPTS_CONFIG[graph_id] else value()
    if isinstance(value, Graph):
        value = value.compile()
    if not isinstance(value, Pregel) and not isinstance(value, RemotePregel):
        raise HTTPException(
            status_code=424,
            detail=f"Graph '{graph_id}' is not valid. Review graph registration.",
        )
    if isinstance(value, RemotePregel):
        value.checkpointer = checkpointer
        value.name = graph_id
        return value

    update = {
        "checkpointer": checkpointer,
        "store": store,
    }
    if value.name == "LangGraph":
        update["name"] = graph_id
    return value.copy(update=update)


def graph_exists(graph_id: str) -> bool:
    """Return whether a graph exists."""
    return graph_id in GRAPHS


def assert_graph_exists(graph_id: str) -> None:
    """Assert that a graph exists."""
    if not graph_exists(graph_id):
        raise HTTPException(status_code=404, detail=f"Graph '{graph_id}' not found")


def get_assistant_id(assistant_id: str) -> str:
    """Check if assistant_id is a valid graph_id. If so, retrieve the
    assistant_id from the graph_id. Otherwise, return the assistant_id
    as is.

    This method is used where the API allows passing both assistant_id
    and graph_id interchangeably.
    """
    if assistant_id in GRAPHS:
        assistant_id = str(uuid5(NAMESPACE_GRAPH, assistant_id))
    return assistant_id


class GraphSpec(NamedTuple):
    """A graph specification."""

    id: str
    path: str | None = None
    module: str | None = None
    variable: str | None = None
    config: dict | None = None


js_bg_tasks: set[asyncio.Task] = set()


def is_js_spec(spec: GraphSpec) -> bool:
    return spec.path is not None and os.path.splitext(spec.path)[1] in (
        ".ts",
        ".mts",
        ".cts",
        ".js",
        ".mjs",
        ".cjs",
    )


def _load_graph_config_from_env() -> dict | None:
    """Return graph config from env."""
    config_str = os.getenv("LANGGRAPH_CONFIG")
    if not config_str:
        return None

    config_per_id = json.loads(config_str)
    if not isinstance(config_per_id, dict):
        raise ValueError("LANGGRAPH_CONFIG must be a JSON object")

    return config_per_id


async def collect_graphs_from_env(register: bool = False) -> None:
    """Return graphs from env."""

    paths_str = os.getenv("LANGSERVE_GRAPHS")
    config_per_graph = _load_graph_config_from_env() or {}

    if paths_str:
        specs = [
            GraphSpec(
                key,
                module=value.split(":")[0],
                variable=value.split(":")[1],
                config=config_per_graph.get(key),
            )
            if "/" not in value
            else GraphSpec(
                key,
                path=value.split(":")[0],
                variable=value.split(":")[1],
                config=config_per_graph.get(key),
            )
            for key, value in json.loads(paths_str).items()
        ]
    else:
        specs = [
            GraphSpec(
                id=graph_path.split("/")[-1].replace(".py", ""),
                path=graph_path,
                config=config_per_graph.get(
                    graph_path.split("/")[-1].replace(".py", "")
                ),
            )
            for graph_path in glob.glob("/graphs/*.py")
        ]

    js_specs = list(filter(is_js_spec, specs))
    py_specs = list(filterfalse(is_js_spec, specs))

    if js_specs:
        import sys

        from langgraph_api.base.js import (
            RemotePregel,
            run_js_process,
            run_remote_checkpointer,
            run_remote_store,
            wait_until_js_ready,
        )

        js_bg_tasks.add(
            asyncio.create_task(
                run_remote_checkpointer(),
                name="remote-checkpointer",
            )
        )
        js_bg_tasks.add(
            asyncio.create_task(
                run_remote_store(),
                name="remote-store",
            )
        )
        js_bg_tasks.add(
            asyncio.create_task(
                run_js_process(paths_str, watch="--reload" in sys.argv[1:]),
                name="remote-graphs",
            )
        )
        for task in js_bg_tasks:
            task.add_done_callback(_handle_exception)

        await wait_until_js_ready()

        for spec in js_specs:
            graph = await RemotePregel.load(graph_id=spec.id)
            if register:
                await register_graph(spec.id, graph, spec.config)

    for spec in py_specs:
        graph = await run_in_executor(None, _graph_from_spec, spec)
        if register:
            await register_graph(spec.id, graph, spec.config)


def _handle_exception(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    finally:
        # if the task died either with exception or not, we should exit
        sys.exit(1)


async def stop_remote_graphs() -> None:
    logger.info("Cancelling remote graphs")
    for task in js_bg_tasks:
        task.cancel()


def verify_graphs() -> None:
    asyncio.run(collect_graphs_from_env())


def _graph_from_spec(spec: GraphSpec) -> GraphValue:
    """Return a graph from a spec."""
    # import the graph module
    if spec.module:
        module = importlib.import_module(spec.module)
    elif spec.path:
        try:
            modname = "".join(choice("abcdefghijklmnopqrstuvwxyz") for _ in range(24))
            modspec = importlib.util.spec_from_file_location(modname, spec.path)
            if modspec is None:
                raise ValueError(f"Could not find python file for graph: {spec}")
            module = importlib.util.module_from_spec(modspec)
            sys.modules[modname] = module
            modspec.loader.exec_module(module)
        except ImportError as e:
            e.add_note(f"Could not import python module for graph: {spec}")
            raise e
    else:
        raise ValueError("Graph specification must have a path or module")

    if spec.variable:
        graph: GraphValue = getattr(module, spec.variable)
        if callable(graph):
            sig = inspect.signature(graph)
            if not sig.parameters:
                if not isinstance(graph(), (Graph, Pregel)):  # noqa: UP038
                    raise ValueError(
                        f"Graph factory function '{spec.variable}' in module '{spec.path}' must return a Graph or Pregel"
                    )
            elif len(sig.parameters) != 1:
                raise ValueError(
                    f"Graph factory function '{spec.variable}' in module '{spec.path}' must take exactly one argument, a RunnableConfig"
                )
        elif isinstance(graph, Graph):
            graph = graph.compile()
        elif isinstance(graph, Pregel):
            pass
        else:
            raise ValueError(
                f"Variable '{spec.variable}' in module '{spec.path}' is not a Graph or Graph factory function"
            )
    else:
        # find the graph in the module
        # - first look for a compiled graph (Pregel)
        # - if not found, look for a Graph and compile it
        for _, member in inspect.getmembers(module):
            if isinstance(member, Pregel):
                graph = member
                break
        else:
            for _, member in inspect.getmembers(module):
                if isinstance(member, Graph):
                    graph = member.compile()
                    break
            else:
                raise ValueError(
                    f"Could not find a Graph in module at path: {spec.path}"
                )

    return graph
