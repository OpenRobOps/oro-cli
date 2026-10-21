# Copyright 2026 InOrbit, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
"""ORO command line interface."""

import json
import logging
import sys
from datetime import datetime
from typing import NoReturn

import click
import yaml
from tabulate import tabulate

from oro_cli import __version__, config
from oro_cli.client import Oro, OroError

logger = logging.getLogger("oro_cli")
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
logger.addHandler(_handler)
logger.setLevel(logging.ERROR)

ENV_CONTEXT_NAME = "(environment)"


def table(rows: list[dict]) -> str:
    # Ids and versions are strings; keep "1.0" and "0123" as typed.
    return tabulate(rows, headers="keys", disable_numparse=True)


def fail(e: Exception) -> NoReturn:
    raise click.ClickException(str(e)) from e


def get_settings() -> config.Settings:
    ctx = click.get_current_context()
    if "settings" not in ctx.obj:
        try:
            ctx.obj["settings"] = config.resolve()
        except config.ConfigError as e:
            fail(e)
        if ctx.obj["verbose"] or ctx.obj["settings"].verbose:
            logger.setLevel(logging.DEBUG)
    return ctx.obj["settings"]


def get_client() -> Oro:
    ctx = click.get_current_context()
    if "client" not in ctx.obj:
        settings = get_settings()
        ctx.obj["client"] = Oro(settings.url, settings.api_key, logger)
    return ctx.obj["client"]


@click.group()
@click.version_option(__version__, prog_name="oro")
@click.option("--verbose", is_flag=True, help="Log HTTP requests and responses to stderr.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """OpenRobOps (ORO) command line tool: configuration as code and fleet queries."""
    ctx.obj = {"verbose": verbose}


@cli.group()
def context() -> None:
    """Manage ORO instances (contexts) and credentials."""


@cli.group()
def get() -> None:
    """Get objects basic information."""


@cli.group()
def describe() -> None:
    """Describe objects with detailed information."""


@cli.group(name="list")
def list_cmd() -> None:
    """List possible values for a given option."""


def _set_current(data: dict, name: str) -> None:
    if name not in data["contexts"]:
        available = ", ".join(sorted(data["contexts"]))
        raise click.ClickException(f"Unknown context {name}. Available: {available}")
    data["current"] = name
    config.save(data)
    click.echo(f"Current context: {name}")


def _load() -> dict:
    try:
        return config.load()
    except config.ConfigError as e:
        fail(e)


@context.command("add")
@click.argument("name")
@click.option("--url", required=True, help="ORO API base URL, e.g. https://oro.example.com/api")
@click.option("--api-key", required=True, help="API key for this instance.")
@click.option("--verbose", is_flag=True, help="Always log HTTP traffic for this context.")
@click.option("--use", "use_it", is_flag=True, help="Make this the current context.")
def context_add(name: str, url: str, api_key: str, verbose: bool, use_it: bool) -> None:
    """Add (or replace) a context."""
    data = _load()
    verb = "replaced" if name in data["contexts"] else "added"
    data["contexts"][name] = {"url": url.rstrip("/"), "api_key": api_key, "verbose": verbose}
    config.save(data)
    click.echo(f"Context {name} {verb}.")
    if use_it or len(data["contexts"]) == 1:
        _set_current(data, name)


@context.command("remove")
@click.argument("name")
def context_remove(name: str) -> None:
    """Remove a context."""
    data = _load()
    if name not in data["contexts"]:
        raise click.ClickException(f"Unknown context {name}.")
    del data["contexts"][name]
    if data["current"] == name:
        data["current"] = None
    config.save(data)
    click.echo(f"Context {name} removed.")


@context.command("list")
def context_list() -> None:
    """List configured contexts (API keys are never shown)."""
    data = _load()
    rows = [
        {
            "": "*" if name == data["current"] else "",
            "name": name,
            "url": ctx["url"],
            "verbose": ctx["verbose"],
        }
        for name, ctx in data["contexts"].items()
    ]
    click.echo(table(rows))


@context.command("current")
def context_current() -> None:
    """Print the current context name."""
    click.echo(get_settings().name or ENV_CONTEXT_NAME)


@context.command("use")
@click.argument("name")
def context_use(name: str) -> None:
    """Switch the current context."""
    _set_current(_load(), name)


cli.add_command(context_use, name="use")


@cli.command()
def whoami() -> None:
    """Show the current context and check that its API key authenticates."""
    settings = get_settings()
    click.echo(f"Context: {settings.name or ENV_CONTEXT_NAME}")
    click.echo(f"URL: {settings.url}")
    click.echo(f"CLI version: {__version__}")
    try:
        response = get_client().http_get("test").json()
    except OroError as e:
        fail(e)
    click.echo(f"Authenticated as user {response.get('user', 'N/A')}")


# --- configuration as code -------------------------------------------------


def strip_scope(item: dict) -> dict:
    """Removes the dummy scope the server stamps on listed items."""
    item.pop("scope", None)
    if isinstance(item.get("metadata"), dict):
        item["metadata"].pop("scope", None)
    return item


def list_kinds() -> list[str]:
    try:
        return sorted(get_client().http_get("configuration/kinds").json()["items"])
    except OroError as e:
        fail(e)


def list_configs(
    kind: str, *, full: bool, include_all: bool = False, config_id: str | None = None
) -> list[dict]:
    params = {"kind": kind, "format": "full" if full else "short"}
    if include_all:
        params["all"] = "true"
    if config_id:
        params["id"] = config_id
    try:
        items = get_client().http_get("configuration/list", params).json()["items"]
    except OroError as e:
        if e.status == 401:
            raise OroError(f"Unauthorized for kind {kind}", 401) from e
        raise
    return [strip_scope(i) for i in items]


@get.command("config")
@click.argument("config_id", required=False)
@click.option("--kind", required=True, help="Configuration kind (see `oro list kinds`).")
@click.option("--json", "as_json", is_flag=True, help="Dump full objects as JSON.")
@click.option("--yaml", "as_yaml", is_flag=True, help="Dump full objects as YAML.")
@click.option("--summary", is_flag=True, help="Show a summary table (default).")
@click.option("--all", "include_all", is_flag=True, help="Include normally hidden elements.")
def get_config(
    config_id: str | None, kind: str, as_json: bool, as_yaml: bool, summary: bool, include_all: bool
) -> None:
    """List configuration objects of a kind."""
    if as_json + as_yaml + summary > 1:
        raise click.BadParameter("Only one of --json, --yaml and --summary can be specified")
    full = as_json or as_yaml
    try:
        items = list_configs(kind, full=full, include_all=include_all, config_id=config_id)
    except OroError as e:
        fail(e)
    if as_json:
        click.echo(json.dumps(items, indent=2))
    elif as_yaml:
        click.echo(yaml.safe_dump_all(items, sort_keys=False), nl=False)
    else:
        click.echo(table(items))


@list_cmd.command("kinds")
def list_kinds_cmd() -> None:
    """List all configuration kinds."""
    click.echo(table([{"name": k} for k in list_kinds()]))


# --- robots ----------------------------------------------------------------


def _robots() -> list[dict]:
    try:
        return get_client().http_get("robots").json()
    except OroError as e:
        fail(e)


def _robot_row(r: dict) -> dict:
    return {"name": r.get("name", ""), "id": r["id"], "agent version": r.get("agentVersion", "")}


@get.command("robots")
def get_robots() -> None:
    """List robots."""
    click.echo(table([_robot_row(r) for r in _robots()]))


@describe.command("robots")
def describe_robots() -> None:
    """List robots with online state and last seen time."""
    rows = [
        {
            **_robot_row(r),
            "online": r.get("agentOnline", False),
            "last seen": (
                datetime.fromtimestamp(r["updatedTs"] / 1000).isoformat()
                if r.get("updatedTs")
                else ""
            ),
        }
        for r in _robots()
    ]
    click.echo(table(rows))
