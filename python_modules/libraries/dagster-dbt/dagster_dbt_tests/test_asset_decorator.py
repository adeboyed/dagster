from __future__ import annotations

from typing import AbstractSet, Any, Mapping, Optional

import pytest
from dagster import AssetKey, DailyPartitionsDefinition, PartitionsDefinition, file_relative_path
from dagster._core.definitions.utils import DEFAULT_IO_MANAGER_KEY
from dagster_dbt.asset_decorator import dbt_assets
from dagster_dbt.cli import DbtManifest

manifest_path = file_relative_path(__file__, "sample_manifest.json")
manifest = DbtManifest.read(path=manifest_path)


@pytest.mark.parametrize(
    "select,exclude,expected_asset_names",
    [
        (
            "*",
            None,
            {
                "sort_by_calories",
                "cold_schema/sort_cold_cereals_by_calories",
                "subdir_schema/least_caloric",
                "sort_hot_cereals_by_calories",
                "orders_snapshot",
                "cereals",
            },
        ),
        (
            "+least_caloric",
            None,
            {"sort_by_calories", "subdir_schema/least_caloric", "cereals"},
        ),
        (
            "sort_by_calories least_caloric",
            None,
            {"sort_by_calories", "subdir_schema/least_caloric"},
        ),
        (
            "tag:bar+",
            None,
            {
                "sort_by_calories",
                "cold_schema/sort_cold_cereals_by_calories",
                "subdir_schema/least_caloric",
                "sort_hot_cereals_by_calories",
                "orders_snapshot",
            },
        ),
        (
            "tag:foo",
            None,
            {"sort_by_calories", "cold_schema/sort_cold_cereals_by_calories"},
        ),
        (
            "tag:foo,tag:bar",
            None,
            {"sort_by_calories"},
        ),
        (
            None,
            "sort_hot_cereals_by_calories",
            {
                "sort_by_calories",
                "cold_schema/sort_cold_cereals_by_calories",
                "subdir_schema/least_caloric",
                "cereals",
                "orders_snapshot",
            },
        ),
        (
            None,
            "+least_caloric",
            {
                "cold_schema/sort_cold_cereals_by_calories",
                "sort_hot_cereals_by_calories",
                "orders_snapshot",
            },
        ),
        (
            None,
            "sort_by_calories least_caloric",
            {
                "cold_schema/sort_cold_cereals_by_calories",
                "sort_hot_cereals_by_calories",
                "orders_snapshot",
                "cereals",
            },
        ),
        (
            None,
            "tag:foo",
            {
                "subdir_schema/least_caloric",
                "sort_hot_cereals_by_calories",
                "orders_snapshot",
                "cereals",
            },
        ),
    ],
)
def test_selections(
    select: Optional[str], exclude: Optional[str], expected_asset_names: AbstractSet[str]
) -> None:
    @dbt_assets(
        manifest=manifest,
        select=select or "fqn:*",
        exclude=exclude,
    )
    def my_dbt_assets():
        ...

    expected_asset_keys = {AssetKey(key.split("/")) for key in expected_asset_names}
    assert my_dbt_assets.keys == expected_asset_keys

    expected_select_tag = "fqn:*" if select is None else select
    assert my_dbt_assets.op.tags.get("dagster-dbt/select") == expected_select_tag
    assert my_dbt_assets.op.tags.get("dagster-dbt/exclude") == exclude


@pytest.mark.parametrize(
    "partitions_def", [None, DailyPartitionsDefinition(start_date="2023-01-01")]
)
def test_partitions_def(partitions_def: Optional[PartitionsDefinition]) -> None:
    @dbt_assets(manifest=manifest, partitions_def=partitions_def)
    def my_dbt_assets():
        ...

    assert my_dbt_assets.partitions_def == partitions_def


@pytest.mark.parametrize("io_manager_key", [None, "my_io_manager_key"])
def test_io_manager_key(io_manager_key: Optional[str]) -> None:
    @dbt_assets(manifest=manifest, io_manager_key=io_manager_key)
    def my_dbt_assets():
        ...

    expected_io_manager_key = DEFAULT_IO_MANAGER_KEY if io_manager_key is None else io_manager_key

    for output_def in my_dbt_assets.node_def.output_defs:
        assert output_def.io_manager_key == expected_io_manager_key


def test_with_asset_key_replacements() -> None:
    class CustomizedDbtManifest(DbtManifest):
        @classmethod
        def node_info_to_asset_key(cls, node_info: Mapping[str, Any]) -> AssetKey:
            return AssetKey(["prefix", *super().node_info_to_asset_key(node_info).path])

    manifest = CustomizedDbtManifest.read(path=manifest_path)

    @dbt_assets(manifest=manifest)
    def my_dbt_assets():
        ...

    assert my_dbt_assets.keys_by_input_name == {}
    assert set(my_dbt_assets.keys_by_output_name.values()) == {
        AssetKey(["prefix", "cereals"]),
        AssetKey(["prefix", "cold_schema", "sort_cold_cereals_by_calories"]),
        AssetKey(["prefix", "subdir_schema", "least_caloric"]),
        AssetKey(["prefix", "orders_snapshot"]),
        AssetKey(["prefix", "sort_hot_cereals_by_calories"]),
        AssetKey(["prefix", "sort_by_calories"]),
    }


def test_with_description_replacements() -> None:
    expected_description = "customized description"

    class CustomizedDbtManifest(DbtManifest):
        @classmethod
        def node_info_to_description(cls, node_info: Mapping[str, Any]) -> str:
            return expected_description

    manifest = CustomizedDbtManifest.read(path=manifest_path)

    @dbt_assets(manifest=manifest)
    def my_dbt_assets():
        ...

    for description in my_dbt_assets.descriptions_by_key.values():
        assert description == expected_description
