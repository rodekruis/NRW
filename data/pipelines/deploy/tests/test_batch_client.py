from datetime import datetime, UTC
from unittest.mock import MagicMock, patch

import pytest
from azure.batch.models import OutputFileUploadCondition
from azure.core.exceptions import ClientAuthenticationError
from batch_client import (
    build_container_task,
    job_output_container_name,
    PipelineConfig,
    submit_pipeline_job,
    TASK_ENVIRONMENT_VARIABLES,
    task_logs_storage_account_url,
)


@pytest.mark.parametrize(
    ("job_id", "expected"),
    [
        ("nrw-floods-20261110-160743", "job-nrw-floods-20261110-160743"),
        (
            "my-_EVEN_MORE_-terrific-job",
            "job-my-even-more-te-68b05a7d8aa6aa65b9a6892c667a6c406a16ad65",
        ),
    ],
)
def test_job_output_container_follows_batch_convention(
    job_id: str, expected: str
) -> None:
    # Arrange
    # Job IDs include the published example with invalid container characters.

    # Act
    container_name = job_output_container_name(job_id)

    # Assert
    assert container_name == expected


def test_task_uploads_logs_using_task_log_convention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    for name in TASK_ENVIRONMENT_VARIABLES:
        monkeypatch.setenv(name, "value")
    monkeypatch.setenv("BATCH_POOL_NODE_IDENTITY_RESOURCE_ID", "node-identity")
    config = PipelineConfig("floods", "pipelines/infra/configs/floods.yaml")

    # Act
    task = build_container_task(
        config, "https://example.blob.core.windows.net/job-123", "manual"
    )

    # Assert
    assert task.output_files is not None
    output = task.output_files[0]
    assert output.file_pattern == "../std*.txt"
    assert (
        output.destination.container.container_url
        == "https://example.blob.core.windows.net/job-123"
    )
    assert output.destination.container.path == "floods-task/$TaskLog"
    assert (
        output.destination.container.identity_reference.resource_id == "node-identity"
    )
    assert (
        output.upload_options.upload_condition
        == OutputFileUploadCondition.TASK_COMPLETION
    )


def test_container_is_created_before_batch_job_and_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    for name in TASK_ENVIRONMENT_VARIABLES:
        monkeypatch.setenv(name, "value")
    monkeypatch.setenv("BATCH_POOL_ID", "pool")
    monkeypatch.setenv("BATCH_POOL_NODE_IDENTITY_RESOURCE_ID", "node-identity")
    monkeypatch.setenv(
        "BATCH_TASK_LOGS_STORAGE_ACCOUNT_URL",
        "https://example.blob.core.windows.net/",
    )
    config = PipelineConfig("floods", "pipelines/infra/configs/floods.yaml")
    batch = MagicMock()
    storage = MagicMock()
    calls = MagicMock()
    calls.attach_mock(storage, "storage")
    calls.attach_mock(batch, "batch")

    # Act
    with patch("batch_client.BlobServiceClient") as storage_client, patch(
        "batch_client.build_token_credential"
    ):
        storage_client.return_value.__enter__.return_value = storage
        job_id = submit_pipeline_job(
            batch, config, datetime(2026, 11, 10, 16, 7, 43, tzinfo=UTC), "manual"
        )

    # Assert
    assert job_id == "nrw-floods-20261110-160743"
    assert [call[0] for call in calls.mock_calls] == [
        "storage.create_container",
        "batch.create_job",
        "batch.create_task",
    ]
    storage.create_container.assert_called_once_with("job-nrw-floods-20261110-160743")
    assert storage_client.call_args.kwargs["account_url"] == (
        "https://example.blob.core.windows.net/"
    )
    task = batch.create_task.call_args.args[1]
    assert task.output_files[0].destination.container.container_url == (
        "https://example.blob.core.windows.net/job-nrw-floods-20261110-160743"
    )


def test_container_creation_failure_does_not_submit_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    for name in TASK_ENVIRONMENT_VARIABLES:
        monkeypatch.setenv(name, "value")
    monkeypatch.setenv("BATCH_POOL_ID", "pool")
    monkeypatch.setenv("BATCH_POOL_NODE_IDENTITY_RESOURCE_ID", "node-identity")
    monkeypatch.setenv(
        "BATCH_TASK_LOGS_STORAGE_ACCOUNT_URL",
        "https://example.blob.core.windows.net/",
    )
    config = PipelineConfig("floods", "pipelines/infra/configs/floods.yaml")
    batch = MagicMock()

    # Act
    with patch("batch_client.BlobServiceClient") as storage_client, patch(
        "batch_client.build_token_credential"
    ):
        storage_client.return_value.__enter__.return_value.create_container.side_effect = ClientAuthenticationError(
            "denied"
        )
        with pytest.raises(ClientAuthenticationError, match="denied"):
            submit_pipeline_job(batch, config, datetime.now(UTC), "manual")

    # Assert
    batch.create_job.assert_not_called()
    batch.create_task.assert_not_called()


@pytest.mark.parametrize(
    "account_url",
    [
        "https://example.blob.core.windows.net",
        "https://example.blob.core.windows.net/?",
        "https://example.blob.core.windows.net/container/",
        "https://example.blob.core.windows.net/?sig=secret",
        "https://example.blob.core.windows.net/#fragment",
        "ftp://example.blob.core.windows.net/",
    ],
)
def test_invalid_storage_account_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch, account_url: str
) -> None:
    # Arrange
    monkeypatch.setenv("BATCH_TASK_LOGS_STORAGE_ACCOUNT_URL", account_url)

    # Act & Assert
    with pytest.raises(ValueError, match="storage account URL ending in /"):
        task_logs_storage_account_url()
