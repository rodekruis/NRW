import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum

from pipelines.infra.data_types.data_config_types import RunOrigin, to_live_or_mock

_log_context: ContextVar[dict[str, str] | None] = ContextVar(
    "pipeline_log_context", default=None
)


@contextmanager
def log_context(
    *, hazard_type: str | None = None, country_code: str | None = None
) -> Iterator[None]:
    context = (_log_context.get() or {}).copy()
    if hazard_type is not None:
        context["hazard_type"] = hazard_type
    if country_code is not None:
        context["country_code"] = country_code
    token = _log_context.set(context)
    try:
        yield
    finally:
        _log_context.reset(token)


# Log tags used to help find and compare logs in Kusto
# Add new tags as needed here with a short comment as to their use.
# Make tags as specific as needed. Kusto queries can easily be written to combine tags.
class LogTag(StrEnum):
    # Timer for measuring large download times
    DOWNLOAD_TIMER = "download_timer"

    # Tag for generated alerts
    # to track creation and if it passes related thresholds
    ALERT_GENERATION = "alert_generation"

    # Tag related to when alert data is sent to the backend
    INFRA_SEND = "infra_send"

    # Generic tags for different sections of the code.
    INFRA = "infra"
    FLOOD_LOGIC = "flood_logic"
    TROPICAL_CYCLONE_LOGIC = "tropical_cyclone_logic"


def log_with_tag(
    logger: logging.Logger,
    tag: LogTag,
    message: str,
    level: int = logging.INFO,
) -> None:
    """
    Log a message prefixed with a tag and live-or-mock marker for fast Kusto
    filtering and readable task output. Run context is attached as structured
    fields for Application Insights, but not included in the task output.
    """
    run_origin = RunOrigin(os.environ.get("PIPELINE_RUN_ORIGIN", RunOrigin.LOCAL))
    source_target = os.environ.get("PIPELINE_SOURCE_TARGET", "unknown")
    live_or_mock = to_live_or_mock(source_target)
    extra = {"run_origin": run_origin.value, **(_log_context.get() or {})}
    job_id = os.environ.get("AZ_BATCH_JOB_ID")
    if job_id:
        extra["job_id"] = job_id
    logger.log(
        level,
        "tag_%s data_%s %s",
        tag.value,
        live_or_mock,
        message,
        extra=extra,
    )


def log_info(logger: logging.Logger, tag: LogTag, message: str) -> None:
    log_with_tag(logger, tag, message, level=logging.INFO)


def log_warning(logger: logging.Logger, tag: LogTag, message: str) -> None:
    log_with_tag(logger, tag, message, level=logging.WARNING)


def log_error(logger: logging.Logger, tag: LogTag, message: str) -> None:
    log_with_tag(logger, tag, message, level=logging.ERROR)
