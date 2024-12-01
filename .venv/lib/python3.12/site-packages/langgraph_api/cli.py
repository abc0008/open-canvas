import contextlib
import json
import logging
import os
import webbrowser

import click

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@contextlib.contextmanager
def patch_environment(**kwargs):
    """Temporarily patch environment variables.

    Args:
        **kwargs: Key-value pairs of environment variables to set.

    Yields:
        None
    """
    original = {}
    try:
        for key, value in kwargs.items():
            original[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_server(
    host: str = "127.0.0.1",
    port: int = 2024,
    reload: bool = False,
    graphs: dict | None = None,
    n_jobs_per_worker: int | None = None,
    env_file: str | None = None,
    open_browser: bool = False,
    debug_port: int | None = None,
):
    """Run the LangGraph API server."""
    import uvicorn

    if debug_port is not None:
        try:
            import debugpy
        except ImportError:
            logger.warning("debugpy is not installed. Debugging will not be available.")
            logger.info("To enable debugging, install debugpy: pip install debugpy")
            return
        debugpy.listen((host, debug_port))
        logger.info(
            f"🐛 Debugger listening on port {debug_port}. Waiting for client to attach..."
        )
        logger.info("To attach the debugger:")
        logger.info("1. Open your python debugger client (e.g., Visual Studio Code).")
        logger.info(
            "2. Use the 'Remote Attach' configuration with the following settings:"
        )
        logger.info("   - Host: 0.0.0.0")
        logger.info(f"   - Port: {debug_port}")
        logger.info("3. Start the debugger to connect to the server.")
        debugpy.wait_for_client()
        logger.info("Debugger attached. Starting server...")

    local_url = f"http://{host}:{port}"
    studio_url = f"https://smith.langchain.com/studio/?baseUrl={local_url}"
    welcome = f"""

        Welcome to

╦  ┌─┐┌┐┌┌─┐╔═╗┬─┐┌─┐┌─┐┬ ┬
║  ├─┤││││ ┬║ ╦├┬┘├─┤├─┘├─┤
╩═╝┴ ┴┘└┘└─┘╚═╝┴└─┴ ┴┴  ┴ ┴

- 🚀 API: \033[36m{local_url}\033[0m
- 🎨 Studio UI: \033[36m{studio_url}\033[0m
- 📚 API Docs: \033[36m{local_url}/docs\033[0m

This in-memory server is designed for development and testing.
For production use, please use LangGraph Cloud.

"""
    logger.info(welcome)
    if open_browser:
        try:
            webbrowser.open(studio_url)
        except Exception as e:
            logger.warning(f"Unable to open browser automatically: {e}")
            logger.warning(
                "To view graphs in browser, please open the Studio UI URL manually."
            )

    with patch_environment(
        MIGRATIONS_PATH="__inmem",
        DATABASE_URI=":memory:",
        REDIS_URI="fake",
        N_JOBS_PER_WORKER=str(n_jobs_per_worker if n_jobs_per_worker else 1),
        LANGSERVE_GRAPHS=json.dumps(graphs) if graphs else None,
        LANGSMITH_LANGGRAPH_API_VARIANT="test",
    ):
        uvicorn.run(
            "langgraph_api.server:app",
            host=host,
            port=port,
            reload=reload,
            env_file=env_file,
            access_log=False,
            log_config={
                "version": 1,
                "incremental": False,
                "disable_existing_loggers": False,
                "formatters": {
                    "simple": {"class": "langgraph_api.base.shared.logging.Formatter"}
                },
                "handlers": {
                    "console": {
                        "class": "logging.StreamHandler",
                        "formatter": "simple",
                        "stream": "ext://sys.stdout",
                    }
                },
                "root": {"handlers": ["console"]},
            },
        )


@click.command()
@click.option("--host", default="127.0.0.1", help="Host to bind the server to")
@click.option("--port", default=2024, type=int, help="Port to bind the server to")
@click.option("--no-reload", is_flag=True, help="Disable auto-reload")
@click.option(
    "--config",
    type=click.Path(exists=True),
    default="langgraph.json",
    help="Path to configuration file",
)
@click.option(
    "--n-jobs-per-worker",
    default=None,
    type=int,
    help="Number of jobs per worker. Default is None (meaning 10)",
)
@click.option(
    "--no-browser",
    is_flag=True,
    help="Disable automatic browser opening",
)
@click.option(
    "--debug-port",
    default=None,
    type=int,
    help="Port for debugger to listen on (default: none)",
)
def main(
    host: str,
    port: int,
    no_reload: bool,
    config: str,
    n_jobs_per_worker: int | None,
    no_browser: bool,
    debug_port: int | None,
):
    """CLI entrypoint for running the LangGraph API server."""
    import json

    with open(config, encoding="utf-8") as f:
        config_data = json.load(f)

    graphs = config_data.get("graphs", {})
    run_server(
        host,
        port,
        not no_reload,
        graphs,
        n_jobs_per_worker=n_jobs_per_worker,
        open_browser=not no_browser,
        debug_port=debug_port,
    )


if __name__ == "__main__":
    main()
