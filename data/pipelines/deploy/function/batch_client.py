"""Helpers to build and submit Azure Batch jobs for the NRW pipeline scheduler.

Authenticates to the Batch data plane over Entra ID (the Batch accounts are
AAD-only; shared-key auth is disabled). Deployed, the Function App's dedicated
user-assigned managed identity (nrw-batch-scheduler-<env>) is used; locally, the
operator's `az login` identity via DefaultAzureCredential.

Targets azure-batch 15.x, the azure-core SDK generation: BatchClient takes a
standard azure-identity TokenCredential directly.
"""

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from azure.batch import BatchClient
from azure.batch.models import (
    BatchAllTasksCompleteMode,
    BatchJobCreateOptions,
    BatchNodeIdentityReference,
    BatchPoolInfo,
    BatchTaskConstraints,
    BatchTaskContainerSettings,
    BatchTaskCreateOptions,
    ContainerWorkingDirectory,
    EnvironmentSetting,
    OutputFile,
    OutputFileBlobContainerDestination,
    OutputFileDestination,
    OutputFileUploadCondition,
    OutputFileUploadConfiguration,
)
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient
from pipeline_run_request import COUNTRY_CODE_PATTERN

CONTAINER_IMAGE_TAG = os.environ.get("NRW_ENVIRONMENT")
CONTAINER_IMAGE = f"nrwdockerregistry.azurecr.io/pipelines:{CONTAINER_IMAGE_TAG}"
TASK_MAX_WALL_CLOCK_TIME = timedelta(hours=10)
TASK_MAX_RETRY_COUNT = 0

# Environment variables forwarded from the Function App settings onto each Batch
# task. Secret values arrive as Key Vault references on the app settings, so the
# resolved values are read from os.environ here.
# If passed like this, these can be read by any user with batch account permissions.
# These secrets are not very sensitive and can already be read from github by more users,
# so this is not considered an issue.
TASK_ENVIRONMENT_VARIABLES = (
    "NRW_ENVIRONMENT",
    "NRW_API_URL",
    "NRW_PIPELINE_API_KEY",
    "GITHUB_DATA_BASE_URL",
    "GLOFAS_FTP_HOST",
    "GLOFAS_FTP_USER",
    "GLOFAS_FTP_PASSWORD",
    "DATA_CACHE_DIR",
    # Set by main.bicep on the Function App; enables pipeline log export to
    # Application Insights inside the Batch task containers.
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
)


# PipelineConfig fields are interpolated into a shell-executed Batch task
# command line, so reject anything outside a conservative allowlist of characters.
HAZARD_TYPE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
CONFIG_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_./-]+$")


@dataclass(frozen=True)
class PipelineConfig:
    """A pipeline YAML config baked into the pipeline container image.

    mock and countries map to the pipeline's --mock and --country flags (see
    pipelines/infra/run_forecasts.py), for manual test runs.
    """

    hazard_type: str
    config_path: str
    mock: int | None = None
    countries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not HAZARD_TYPE_PATTERN.fullmatch(self.hazard_type):
            raise ValueError(f"Invalid hazard type '{self.hazard_type}'.")
        if ".." in self.config_path or not CONFIG_PATH_PATTERN.fullmatch(
            self.config_path
        ):
            raise ValueError(f"Invalid config path '{self.config_path}'.")
        if self.mock is not None and self.mock not in (0, 1):
            raise ValueError(f"Invalid mock alert count '{self.mock}'.")

        for country in self.countries:
            if not COUNTRY_CODE_PATTERN.fullmatch(country):
                raise ValueError(f"Invalid country '{country}'.")


def submit_pipeline_job(
    batch_client: BatchClient,
    pipeline_config: PipelineConfig,
    run_started_at: datetime,
    run_origin: str,
) -> str:
    """Create one Batch job with a single container task for the given hazard."""
    job_id = build_job_id(pipeline_config, run_started_at)
    container_name = job_output_container_name(job_id)
    storage_account_url = task_logs_storage_account_url()
    container_url = f"{storage_account_url}{container_name}"
    task = build_container_task(pipeline_config, container_url, run_origin)
    job = BatchJobCreateOptions(
        id=job_id,
        pool_info=BatchPoolInfo(pool_id=require_app_setting("BATCH_POOL_ID")),
        all_tasks_complete_mode=BatchAllTasksCompleteMode.TERMINATE_JOB,
    )
    with BlobServiceClient(
        account_url=storage_account_url, credential=build_token_credential()
    ) as storage_client:
        storage_client.create_container(container_name)
    batch_client.create_job(job)
    batch_client.create_task(job_id, task)
    return job_id


def create_batch_client() -> BatchClient:
    """Build a Batch data-plane client authenticated over Entra ID."""
    return BatchClient(
        endpoint=require_app_setting("BATCH_ACCOUNT_URL"),
        credential=build_token_credential(),
    )


def build_job_id(pipeline_config: PipelineConfig, run_started_at: datetime) -> str:
    """Deterministic prefix plus hazard and timestamp, unique per run."""
    return f"nrw-{pipeline_config.hazard_type}-{run_started_at:%Y%m%d-%H%M%S}"


def job_output_container_name(job_id: str) -> str:
    normalized_id = job_id.lower()
    container_name = f"job-{normalized_id}"
    if len(container_name) <= 63 and re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*", container_name
    ):
        return container_name

    job_hash = hashlib.sha1(normalized_id.encode(), usedforsecurity=False).hexdigest()
    prefix = re.sub(r"[_:-]+", "-", normalized_id).strip("-") or "job"
    prefix = prefix[:15].rstrip("-")
    return f"job-{prefix}-{job_hash}"


def task_logs_storage_account_url() -> str:
    account_url = require_app_setting("BATCH_TASK_LOGS_STORAGE_ACCOUNT_URL")
    parsed_url = urlsplit(account_url)
    if (
        parsed_url.scheme not in ("http", "https")
        or not parsed_url.netloc
        or parsed_url.path != "/"
        or not account_url.endswith("/")
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ValueError(
            "BATCH_TASK_LOGS_STORAGE_ACCOUNT_URL must be a plain storage account URL ending in /."
        )
    return account_url


def build_container_task(
    pipeline_config: PipelineConfig, container_url: str, run_origin: str
) -> BatchTaskCreateOptions:
    """Container task mirroring local invocation: `pipeline --config <path>`."""
    task_id = f"{pipeline_config.hazard_type}-task"
    return BatchTaskCreateOptions(
        id=task_id,
        command_line=build_command_line(pipeline_config),
        container_settings=BatchTaskContainerSettings(
            image_name=CONTAINER_IMAGE,
            # Use the image WORKDIR (/home/pipelines/app) so the relative config
            # path resolves; Batch otherwise defaults to the task working directory.
            working_directory=ContainerWorkingDirectory.CONTAINER_IMAGE_DEFAULT,
        ),
        environment_settings=task_environment_settings(run_origin),
        constraints=BatchTaskConstraints(
            max_wall_clock_time=TASK_MAX_WALL_CLOCK_TIME,
            max_task_retry_count=TASK_MAX_RETRY_COUNT,
        ),
        output_files=task_output_files(task_id, container_url),
    )


def build_command_line(pipeline_config: PipelineConfig) -> str:
    """Render the pipeline CLI invocation, e.g. `pipeline --config <path> --mock 0 --country PHL`."""
    data_cache_dir = require_app_setting("DATA_CACHE_DIR").rstrip("/")
    parts = [
        "pipeline",
        "--config",
        pipeline_config.config_path,
        "--output-path",
        f"{data_cache_dir}/pipeline-output",
    ]
    if pipeline_config.mock is not None:
        parts += ["--mock", str(pipeline_config.mock)]
    if pipeline_config.countries:
        parts += ["--country", ",".join(pipeline_config.countries)]
    return " ".join(parts)


def task_environment_settings(run_origin: str) -> list[EnvironmentSetting]:
    """Read the pipeline environment variables from the Function App settings."""
    return [
        *(
            EnvironmentSetting(name=name, value=require_app_setting(name))
            for name in TASK_ENVIRONMENT_VARIABLES
        ),
        EnvironmentSetting(name="PIPELINE_RUN_ORIGIN", value=run_origin),
    ]


def task_output_files(task_id: str, container_url: str) -> list[OutputFile]:
    """Write the Batch stdout.txt/stderr.txt files to blob storage"""
    node_identity_resource_id = require_app_setting(
        "BATCH_POOL_NODE_IDENTITY_RESOURCE_ID"
    )
    return [
        OutputFile(
            file_pattern="../std*.txt",
            destination=OutputFileDestination(
                container=OutputFileBlobContainerDestination(
                    container_url=container_url,
                    path=f"{task_id}/$TaskLog",
                    identity_reference=BatchNodeIdentityReference(
                        resource_id=node_identity_resource_id
                    ),
                )
            ),
            upload_options=OutputFileUploadConfiguration(
                upload_condition=OutputFileUploadCondition.TASK_COMPLETION
            ),
        )
    ]


def build_token_credential() -> TokenCredential:
    """Managed identity when deployed; the operator's login identity locally."""
    managed_identity_client_id = os.environ.get("AZURE_CLIENT_ID")
    if managed_identity_client_id:
        return ManagedIdentityCredential(client_id=managed_identity_client_id)
    return DefaultAzureCredential()


def require_app_setting(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required app setting '{name}' is not set.")
    return value
