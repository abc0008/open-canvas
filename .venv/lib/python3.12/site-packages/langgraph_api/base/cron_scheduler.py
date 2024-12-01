import asyncio
from datetime import datetime
from random import random

import croniter
import structlog
from langchain_core.runnables.config import run_in_executor

from langgraph_api.base.models.run import create_valid_run
from langgraph_api.storage.database import connect
from langgraph_api.storage.ops import Crons
from langgraph_api.storage.retry import retry_db

logger = structlog.stdlib.get_logger(__name__)

SLEEP_TIME = 5


def _next_cron_date(schedule: str, base_time: datetime) -> datetime:
    cron_iter = croniter.croniter(schedule, base_time)
    return cron_iter.get_next(datetime)


@retry_db
async def cron_scheduler():
    logger.info("Starting cron scheduler")
    while True:
        try:
            async with connect() as conn:
                async for cron in Crons.next(conn):
                    logger.debug(f"Scheduling cron run {cron}")
                    try:
                        run_payload = cron["payload"]
                        run = await create_valid_run(
                            conn,
                            thread_id=str(cron.get("thread_id"))
                            if cron.get("thread_id")
                            else None,
                            payload=run_payload,
                            user_id=cron.get("user_id"),
                            headers={},
                        )
                        if not run:
                            logger.error(
                                "Run not created for cron_id={} payload".format(
                                    cron["cron_id"],
                                )
                            )
                    except Exception as e:
                        logger.error(
                            "Error scheduling cron run cron_id={}".format(
                                cron["cron_id"]
                            ),
                            exc_info=e,
                        )
                    next_run_date = await run_in_executor(
                        None, _next_cron_date, cron["schedule"], cron["now"]
                    )
                    await Crons.set_next_run_date(conn, cron["cron_id"], next_run_date)

            await asyncio.sleep(SLEEP_TIME)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Error in cron_scheduler", exc_info=e)
            await asyncio.sleep(SLEEP_TIME + random())
