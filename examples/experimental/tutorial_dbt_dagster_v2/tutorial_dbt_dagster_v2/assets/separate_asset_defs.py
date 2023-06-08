from __future__ import annotations

from typing import TYPE_CHECKING

from dagster_dbt.asset_decorator import dbt_assets
from dagster_dbt.cli import DbtCli, DbtManifest

from . import MANIFEST_PATH

if TYPE_CHECKING:
    from dagster import OpExecutionContext

manifest = DbtManifest.read(path=MANIFEST_PATH)


@dbt_assets(manifest=manifest, select="resource_type:seed")
def dbt_seed_assets(context: OpExecutionContext, dbt: DbtCli):
    yield from dbt.cli(["seed"], manifest=manifest, context=context).stream()


@dbt_assets(manifest=manifest, select="fqn:staging.*")
def dbt_staging_assets(context: OpExecutionContext, dbt: DbtCli):
    dbt_commands = [
        ["run"],
        ["test"],
    ]

    for dbt_command in dbt_commands:
        yield from dbt.cli(dbt_command, manifest=manifest, context=context).stream()


@dbt_assets(manifest=manifest, select="fqn:customers fqn:orders")
def my_dbt_assets(context: OpExecutionContext, dbt: DbtCli):
    dbt_commands = [
        ["run"],
        ["test"],
    ]

    for dbt_command in dbt_commands:
        yield from dbt.cli(dbt_command, manifest=manifest, context=context).stream()
