import logging
from unittest.mock import patch

import pytest

from pipelines.infra.utils.nrw_logger import log_context, log_info, LogTag


def test_log_includes_pipeline_provenance() -> None:
    logger = logging.getLogger("test_nrw_logger")

    with patch.dict(
        "os.environ",
        {"PIPELINE_RUN_ORIGIN": "scheduled", "PIPELINE_SOURCE_TARGET": "live"},
    ), patch.object(logger, "log") as log:
        log_info(logger, LogTag.INFRA, "pipeline started")

    log.assert_called_once_with(
        logging.INFO,
        "tag_%s data_%s %s",
        "infra",
        "live",
        "pipeline started",
        extra={
            "run_origin": "scheduled",
        },
    )


def test_log_defaults_to_local_source() -> None:
    logger = logging.getLogger("test_nrw_logger")

    with patch.dict("os.environ", {}, clear=True), patch.object(logger, "log") as log:
        log_info(logger, LogTag.INFRA, "pipeline started")

    assert log.call_args.args == (
        logging.INFO,
        "tag_%s data_%s %s",
        "infra",
        "mock",
        "pipeline started",
    )
    assert log.call_args.kwargs["extra"] == {
        "run_origin": "local",
    }


def test_rejects_unknown_run_origin() -> None:
    logger = logging.getLogger("test_nrw_logger")

    with patch.dict("os.environ", {"PIPELINE_RUN_ORIGIN": "unexpected"}):
        try:
            log_info(logger, LogTag.INFRA, "pipeline started")
        except ValueError as error:
            assert "unexpected" in str(error)
        else:
            raise AssertionError("Unknown run origin should be rejected")


def test_log_context_is_restored_after_exception(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Arrange
    monkeypatch.delenv("AZ_BATCH_JOB_ID", raising=False)
    logger = logging.getLogger("test_nrw_context_restore")

    # Act
    with caplog.at_level(logging.INFO):
        with log_context(hazard_type="floods"):
            with pytest.raises(RuntimeError, match="failed"), log_context(
                country_code="KEN"
            ):
                log_info(logger, LogTag.INFRA, "country")
                raise RuntimeError("failed")
            log_info(logger, LogTag.INFRA, "after country")
        log_info(logger, LogTag.INFRA, "after hazard")

    # Assert
    country_record, after_country, after_hazard = caplog.records
    assert country_record.__dict__["country_code"] == "KEN"
    assert country_record.__dict__["hazard_type"] == "floods"
    assert after_country.__dict__["hazard_type"] == "floods"
    assert not hasattr(after_country, "country_code")
    assert not hasattr(after_hazard, "hazard_type")
    assert not hasattr(after_hazard, "job_id")
