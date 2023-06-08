from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

import pytest
from dagster import AssetObservation, Output
from dagster_dbt.cli import DbtCli, DbtCliEventMessage, DbtManifest

from ..conftest import TEST_PROJECT_DIR

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

pytest.importorskip("dbt.version", minversion="1.4")


manifest_path = f"{TEST_PROJECT_DIR}/manifest.json"
manifest = DbtManifest.read(path=manifest_path)


@pytest.mark.parametrize("global_config", [[], ["--debug"]])
@pytest.mark.parametrize("command", ["run", "parse"])
def test_dbt_cli(global_config: List[str], command: str) -> None:
    dbt = DbtCli(project_dir=TEST_PROJECT_DIR, global_config=global_config)
    dbt_cli_task = dbt.cli([command], manifest=manifest)

    list(dbt_cli_task.stream())

    assert dbt_cli_task.process.args == ["dbt", *global_config, command]
    assert dbt_cli_task.is_successful()
    assert dbt_cli_task.process.returncode == 0


def test_dbt_cli_failure() -> None:
    dbt = DbtCli(project_dir=TEST_PROJECT_DIR)
    dbt_cli_task = dbt.cli(["run", "--profiles-dir", "nonexistent"], manifest=manifest)

    assert not dbt_cli_task.is_successful()
    assert dbt_cli_task.process.returncode == 2


def test_dbt_cli_get_artifact() -> None:
    dbt = DbtCli(project_dir=TEST_PROJECT_DIR)

    dbt_cli_task_1 = dbt.cli(["run"], manifest=manifest)
    dbt_cli_task_1.wait()

    dbt_cli_task_2 = dbt.cli(["compile"], manifest=manifest)
    dbt_cli_task_2.wait()

    # `dbt run` produces a manifest.json and run_results.json
    manifest_json_1 = dbt_cli_task_1.get_artifact("manifest.json")
    assert manifest_json_1
    assert dbt_cli_task_1.get_artifact("run_results.json")

    # `dbt compile` produces a manifest.json and run_results.json
    manifest_json_2 = dbt_cli_task_2.get_artifact("manifest.json")
    assert manifest_json_2
    assert dbt_cli_task_2.get_artifact("run_results.json")

    # `dbt compile` does not produce a sources.json
    with pytest.raises(Exception):
        dbt_cli_task_2.get_artifact("sources.json")

    # Artifacts are stored in separate paths by manipulating DBT_TARGET_PATH.
    # As a result, their contents should be different, and newer artifacts
    # should not overwrite older ones.
    assert manifest_json_1 != manifest_json_2


def test_dbt_cli_subsetted_execution(mocker: MockerFixture) -> None:
    mock_context = mocker.MagicMock()
    mock_selected_output_names = ["least_caloric", "sort_by_calories"]

    type(mock_context.op).tags = mocker.PropertyMock(return_value={})
    type(mock_context).selected_output_names = mocker.PropertyMock(
        return_value=mock_selected_output_names
    )

    dbt = DbtCli(project_dir=TEST_PROJECT_DIR)
    dbt_cli_task = dbt.cli(["run"], manifest=manifest, context=mock_context)

    dbt_cli_task.wait()

    assert dbt_cli_task.process.args == [
        "dbt",
        "run",
        "--select",
        (
            "fqn:dagster_dbt_test_project.subdir.least_caloric"
            " fqn:dagster_dbt_test_project.sort_by_calories"
        ),
    ]
    assert dbt_cli_task.process.returncode is not None


@pytest.mark.parametrize("exclude", [None, "fqn:dagster_dbt_test_project.subdir.least_caloric"])
def test_dbt_cli_default_selection(mocker: MockerFixture, exclude: Optional[str]) -> None:
    mock_context = mocker.MagicMock()
    mock_selected_output_names = ["least_caloric", "sort_by_calories"]

    type(mock_context.op).tags = mocker.PropertyMock(
        return_value={
            "dagster-dbt/select": "fqn:*",
            **({"dagster-dbt/exclude": exclude} if exclude else {}),
        }
    )
    type(mock_context).selected_output_names = mocker.PropertyMock(
        return_value=mock_selected_output_names
    )
    mock_context.assets_def.node_keys_by_output_name.__len__.return_value = len(
        mock_selected_output_names
    )

    dbt = DbtCli(project_dir=TEST_PROJECT_DIR)
    dbt_cli_task = dbt.cli(["run"], manifest=manifest, context=mock_context)

    dbt_cli_task.wait()

    expected_args = ["dbt", "run", "--select", "fqn:*"]
    if exclude:
        expected_args += ["--exclude", exclude]

    assert dbt_cli_task.process.args == expected_args
    assert dbt_cli_task.process.returncode is not None


@pytest.mark.parametrize(
    "data",
    [
        {},
        {
            "node_info": {
                "unique_id": "a.b.c",
                "resource_type": "model",
                "node_status": "failure",
                "node_finished_at": "2024-01-01T00:00:00Z",
            }
        },
        {
            "node_info": {
                "unique_id": "a.b.c",
                "resource_type": "macro",
                "node_status": "success",
                "node_finished_at": "2024-01-01T00:00:00Z",
            }
        },
        {
            "node_info": {
                "unique_id": "a.b.c",
                "resource_type": "model",
                "node_status": "failure",
            }
        },
        {
            "node_info": {
                "unique_id": "a.b.c",
                "resource_type": "test",
                "node_status": "success",
            }
        },
    ],
    ids=[
        "node info missing",
        "node status failure",
        "not refable",
        "not successful execution",
        "not finished test execution",
    ],
)
def test_no_default_asset_events_emitted(data: dict) -> None:
    manifest = DbtManifest(raw_manifest={})
    asset_events = DbtCliEventMessage(event={"data": data}).to_default_asset_events(
        manifest=manifest
    )

    assert list(asset_events) == []


def test_to_default_asset_output_events() -> None:
    manifest = DbtManifest(raw_manifest={})
    event = {
        "data": {
            "node_info": {
                "unique_id": "a.b.c",
                "resource_type": "model",
                "node_status": "success",
                "node_finished_at": "2024-01-01T00:00:00Z",
            }
        }
    }
    asset_events = list(DbtCliEventMessage(event=event).to_default_asset_events(manifest=manifest))

    assert len(asset_events) == 1
    assert all(isinstance(e, Output) for e in asset_events)


def test_to_default_asset_observation_events() -> None:
    manifest = DbtManifest(
        raw_manifest={
            "nodes": {
                "a.b.c.d": {
                    "resource_type": "model",
                    "config": {},
                    "name": "model",
                }
            },
            "sources": {
                "a.b.c.d.e": {
                    "resource_type": "source",
                    "source_name": "test",
                    "name": "source",
                }
            },
            "parent_map": {
                "a.b.c": [
                    "a.b.c.d",
                    "a.b.c.d.e",
                ]
            },
        }
    )
    event = {
        "data": {
            "node_info": {
                "unique_id": "a.b.c",
                "resource_type": "test",
                "node_status": "success",
                "node_finished_at": "2024-01-01T00:00:00Z",
            }
        }
    }
    asset_events = list(DbtCliEventMessage(event=event).to_default_asset_events(manifest=manifest))

    assert len(asset_events) == 2
    assert all(isinstance(e, AssetObservation) for e in asset_events)
