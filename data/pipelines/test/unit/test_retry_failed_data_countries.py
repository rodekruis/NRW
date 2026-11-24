import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from shared.country_data import CountryCodeIso3

from pipelines.infra import run_forecasts as run_forecasts_module
from pipelines.infra.data_types.data_config_types import (
    CountryRunConfig,
    DataSource,
    DataSourceConfig,
    OutputMode,
    PipelineRunConfig,
)
from pipelines.infra.data_types.enums import HazardType
from pipelines.infra.run_forecasts import (
    _has_retryable_source_failure,
    _log_country_result,
    _log_failed_countries,
    _retry_failed_data_countries,
    _run_country,
    CountryRunResult,
    ForecastRunContext,
)
from pipelines.infra.utils.nrw_logger import log_info, LogTag


def _make_country(
    code: str, data_sources: list[DataSourceConfig] | None = None
) -> CountryRunConfig:
    return CountryRunConfig(
        country_code_iso_3=CountryCodeIso3(code),
        target_admin_level=3,
        data_sources=data_sources or [],
    )


def _make_source(code: str, source: DataSource, retryable: bool) -> DataSourceConfig:
    return DataSourceConfig(
        country_code_iso_3=CountryCodeIso3(code),
        source=source,
        hazard_type=HazardType.FLOODS,
        retryable=retryable,
    )


def _make_context() -> ForecastRunContext:
    return ForecastRunContext(
        hazard_fn=lambda *args: None,
        hazard_type=HazardType.FLOODS,
        issued_at=None,
        output_mode=OutputMode.API,
        output_path="output",
        api_client=MagicMock(),
        local_data=None,
        local_data_date=None,
    )


class TestRetryFailedDataCountries:
    def test_data_failure_is_retried_after_a_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        failed_country = _make_country("KEN")
        succeeded_country = _make_country("ETH")
        results = [
            CountryRunResult(
                failed_country,
                ["FTP timeout"],
                is_retryable_data_failure=True,
                data_load_succeeded=False,
            ),
            CountryRunResult(
                succeeded_country,
                [],
                is_retryable_data_failure=False,
                data_load_succeeded=True,
            ),
        ]

        def fake_run_country(
            _context: ForecastRunContext, country: CountryRunConfig
        ) -> CountryRunResult:
            return CountryRunResult(
                country, [], is_retryable_data_failure=False, data_load_succeeded=True
            )

        monkeypatch.setattr(run_forecasts_module, "_run_country", fake_run_country)

        # Act
        retried = _retry_failed_data_countries(_make_context(), results)

        # Assert
        assert all(not result.errors for result in retried)

    def test_no_retry_when_no_country_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        results = [
            CountryRunResult(
                _make_country("KEN"),
                ["FTP timeout"],
                is_retryable_data_failure=True,
                data_load_succeeded=False,
            ),
            CountryRunResult(
                _make_country("ETH"),
                ["FTP timeout"],
                is_retryable_data_failure=True,
                data_load_succeeded=False,
            ),
        ]
        retried_countries: list[CountryRunConfig] = []

        def fake_run_country(
            _context: ForecastRunContext, country: CountryRunConfig
        ) -> CountryRunResult:
            retried_countries.append(country)
            return CountryRunResult(
                country, [], is_retryable_data_failure=False, data_load_succeeded=True
            )

        monkeypatch.setattr(run_forecasts_module, "_run_country", fake_run_country)

        # Act
        retried = _retry_failed_data_countries(_make_context(), results)

        # Assert
        assert retried is results
        assert retried_countries == []
        assert all(result.errors for result in retried)

    def test_non_retryable_failure_is_not_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        succeeded_country = _make_country("KEN")
        failed_country = _make_country("ETH")
        results = [
            CountryRunResult(
                succeeded_country,
                [],
                is_retryable_data_failure=False,
                data_load_succeeded=True,
            ),
            CountryRunResult(
                failed_country,
                ["submission failed"],
                is_retryable_data_failure=False,
                data_load_succeeded=True,
            ),
        ]
        retried_countries: list[CountryRunConfig] = []

        def fake_run_country(
            _context: ForecastRunContext, country: CountryRunConfig
        ) -> CountryRunResult:
            retried_countries.append(country)
            return CountryRunResult(
                country, [], is_retryable_data_failure=False, data_load_succeeded=True
            )

        monkeypatch.setattr(run_forecasts_module, "_run_country", fake_run_country)

        # Act
        retried = _retry_failed_data_countries(_make_context(), results)

        # Assert
        assert retried_countries == []
        failed_result = next(
            result for result in retried if result.country is failed_country
        )
        assert failed_result.errors == ["submission failed"]

    def test_retry_result_replaces_original_outcome(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        failed_country = _make_country("KEN")
        succeeded_country = _make_country("ETH")
        results = [
            CountryRunResult(
                failed_country,
                ["FTP timeout"],
                is_retryable_data_failure=True,
                data_load_succeeded=False,
            ),
            CountryRunResult(
                succeeded_country,
                [],
                is_retryable_data_failure=False,
                data_load_succeeded=True,
            ),
        ]

        def fake_run_country(
            _context: ForecastRunContext, country: CountryRunConfig
        ) -> CountryRunResult:
            return CountryRunResult(
                country,
                ["still failing"],
                is_retryable_data_failure=True,
                data_load_succeeded=False,
            )

        monkeypatch.setattr(run_forecasts_module, "_run_country", fake_run_country)

        # Act
        retried = _retry_failed_data_countries(_make_context(), results)

        # Assert
        failed_result = next(
            result for result in retried if result.country is failed_country
        )
        succeeded_result = next(
            result for result in retried if result.country is succeeded_country
        )
        assert failed_result.errors == ["still failing"]
        assert succeeded_result.errors == []

    def test_retry_runs_when_a_country_loaded_data_but_failed_submission(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        failed_country = _make_country("KEN")
        loaded_but_submission_failed = _make_country("ETH")
        results = [
            CountryRunResult(
                failed_country,
                ["FTP timeout"],
                is_retryable_data_failure=True,
                data_load_succeeded=False,
            ),
            CountryRunResult(
                loaded_but_submission_failed,
                ["submission failed"],
                is_retryable_data_failure=False,
                data_load_succeeded=True,
            ),
        ]

        def fake_run_country(
            _context: ForecastRunContext, country: CountryRunConfig
        ) -> CountryRunResult:
            return CountryRunResult(
                country, [], is_retryable_data_failure=False, data_load_succeeded=True
            )

        monkeypatch.setattr(run_forecasts_module, "_run_country", fake_run_country)

        # Act
        retried = _retry_failed_data_countries(_make_context(), results)

        # Assert
        failed_result = next(
            result for result in retried if result.country is failed_country
        )
        assert failed_result.errors == []


class _FakeDataProvider:
    def __init__(self, loaded_data: dict[DataSource, object]) -> None:
        self.loaded_data = loaded_data

    def try_load_data(self, _country: CountryRunConfig) -> tuple[bool, list[str]]:
        return False, ["load failed"]


class TestRunCountryRetryableFlag:
    def test_retryable_source_failure_is_flagged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        country = _make_country(
            "KEN",
            [_make_source("KEN", DataSource.GLOFAS_DISCHARGE_FTP, retryable=True)],
        )
        loaded_data: dict[DataSource, object] = {
            DataSource.GLOFAS_DISCHARGE_FTP: SimpleNamespace(error="timeout"),
        }
        monkeypatch.setattr(
            run_forecasts_module,
            "DataProvider",
            lambda *args, **kwargs: _FakeDataProvider(loaded_data),
        )

        # Act
        result = _run_country(_make_context(), country)

        # Assert
        assert result.is_retryable_data_failure is True
        assert result.data_load_succeeded is False

    def test_non_retryable_source_failure_is_not_flagged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        country = _make_country(
            "KEN",
            [_make_source("KEN", DataSource.POPULATION_NRW_API, retryable=False)],
        )
        loaded_data: dict[DataSource, object] = {
            DataSource.POPULATION_NRW_API: SimpleNamespace(error="not found"),
        }
        monkeypatch.setattr(
            run_forecasts_module,
            "DataProvider",
            lambda *args, **kwargs: _FakeDataProvider(loaded_data),
        )

        # Act
        result = _run_country(_make_context(), country)

        # Assert
        assert result.is_retryable_data_failure is False
        assert result.data_load_succeeded is False


class TestHasRetryableSourceFailure:
    def test_false_when_the_failed_source_is_not_retryable(self) -> None:
        # Arrange
        country = _make_country(
            "KEN",
            [
                _make_source("KEN", DataSource.GLOFAS_DISCHARGE_FTP, retryable=True),
                _make_source("KEN", DataSource.POPULATION_NRW_API, retryable=False),
            ],
        )
        data_provider = _FakeDataProvider(
            {
                DataSource.GLOFAS_DISCHARGE_FTP: SimpleNamespace(error=None),
                DataSource.POPULATION_NRW_API: SimpleNamespace(error="not found"),
            }
        )

        # Act
        result = _has_retryable_source_failure(country, data_provider)  # type: ignore[arg-type]

        # Assert
        assert result is False


class TestFailureLogging:
    def test_country_logs_include_context_during_runs_and_deferred_failures(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Arrange
        countries = [_make_country("KEN"), _make_country("ETH")]
        config = PipelineRunConfig(
            hazard_type=HazardType.FLOODS,
            country_configs={
                country.country_code_iso_3: country for country in countries
            },
        )
        reader = SimpleNamespace(config=config, load_all=lambda _path: True)
        monkeypatch.setattr(
            run_forecasts_module, "ConfigReader", lambda **_kwargs: reader
        )
        monkeypatch.setattr(run_forecasts_module, "ApiClient", MagicMock())
        monkeypatch.setenv("AZ_BATCH_JOB_ID", "job-123")

        def fake_run_country(
            _context: ForecastRunContext, country: CountryRunConfig
        ) -> CountryRunResult:
            log_info(run_forecasts_module.logger, LogTag.INFRA, "inside country")
            errors = ["failure"] if country.country_code_iso_3 == "KEN" else []
            return CountryRunResult(country, errors, bool(errors), not errors)

        monkeypatch.setattr(run_forecasts_module, "_run_country", fake_run_country)

        # Act
        with caplog.at_level(logging.INFO):
            errors = run_forecasts_module.run_forecasts("unused")

        # Assert
        assert errors == ["failure"]
        records = caplog.records
        assert all(record.__dict__["job_id"] == "job-123" for record in records)
        assert all(record.__dict__["hazard_type"] == "floods" for record in records)
        inside = [record for record in records if "inside country" in record.message]
        assert [record.__dict__["country_code"] for record in inside] == [
            "KEN",
            "ETH",
            "KEN",
        ]
        failures = [record for record in records if "Errors for" in record.message]
        assert len(failures) == 1
        assert failures[0].__dict__["country_code"] == "KEN"
        start = next(record for record in records if "Start 'floods'" in record.message)
        assert not hasattr(start, "country_code")

    def test_recovered_country_is_not_logged_as_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        errors_logged: list[str] = []
        infos_logged: list[str] = []
        monkeypatch.setattr(
            run_forecasts_module,
            "log_error",
            lambda _logger, _tag, message: errors_logged.append(message),
        )
        monkeypatch.setattr(
            run_forecasts_module,
            "log_info",
            lambda _logger, _tag, message: infos_logged.append(message),
        )
        failed = CountryRunResult(
            _make_country("KEN"),
            ["FTP timeout"],
            is_retryable_data_failure=True,
            data_load_succeeded=False,
        )
        succeeded = CountryRunResult(
            _make_country("ETH"),
            [],
            is_retryable_data_failure=False,
            data_load_succeeded=True,
        )

        # Act
        _log_country_result(_make_context(), failed)
        _log_country_result(_make_context(), succeeded)

        # Assert
        assert errors_logged == []
        assert any("ETH" in message for message in infos_logged)

    def test_still_failing_countries_are_logged_once_after_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        errors_logged: list[str] = []
        monkeypatch.setattr(
            run_forecasts_module,
            "log_error",
            lambda _logger, _tag, message: errors_logged.append(message),
        )
        results = [
            CountryRunResult(
                _make_country("KEN"),
                ["FTP timeout"],
                is_retryable_data_failure=True,
                data_load_succeeded=False,
            ),
            CountryRunResult(
                _make_country("ETH"),
                [],
                is_retryable_data_failure=False,
                data_load_succeeded=True,
            ),
        ]

        # Act
        _log_failed_countries(results)

        # Assert
        assert len(errors_logged) == 1
        assert "KEN" in errors_logged[0]
