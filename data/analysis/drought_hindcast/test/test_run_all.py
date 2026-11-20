import importlib
import pkgutil

import analysis.drought_hindcast
import pytest
from analysis.drought_hindcast.run_all import (
    ANALYSIS_STEPS,
    DATA_COLLECTION_STEPS,
    get_step_name,
    select_steps,
)

RUNNER_MODULE_NAME = "run_all"


def test_every_script_of_the_analysis_is_a_step() -> None:
    # Arrange
    script_names = {
        module.name
        for module in pkgutil.iter_modules(analysis.drought_hindcast.__path__)
        if not module.ispkg
        and module.name != RUNNER_MODULE_NAME
        and hasattr(
            importlib.import_module(f"analysis.drought_hindcast.{module.name}"), "main"
        )
    }

    # Act
    step_names = [
        get_step_name(step) for step in (*DATA_COLLECTION_STEPS, *ANALYSIS_STEPS)
    ]

    # Assert
    assert set(step_names) == script_names
    assert len(step_names) == len(set(step_names))


def test_data_is_collected_first_and_only_when_asked() -> None:
    # Arrange: the steps are the constants of the module.

    # Act
    analysis_only = select_steps(collects_data=False, first_step_name=None)
    with_data_collection = select_steps(collects_data=True, first_step_name=None)

    # Assert
    assert analysis_only == ANALYSIS_STEPS
    assert with_data_collection == (*DATA_COLLECTION_STEPS, *ANALYSIS_STEPS)


def test_a_run_resumes_at_the_named_step() -> None:
    # Arrange
    first_step_name = get_step_name(ANALYSIS_STEPS[3])

    # Act
    steps = select_steps(collects_data=False, first_step_name=first_step_name)

    # Assert
    assert steps == ANALYSIS_STEPS[3:]


def test_a_step_that_is_not_run_cannot_be_resumed_at() -> None:
    # Arrange
    data_collection_step_name = get_step_name(DATA_COLLECTION_STEPS[0])

    # Act and assert
    with pytest.raises(ValueError, match=data_collection_step_name):
        select_steps(collects_data=False, first_step_name=data_collection_step_name)
