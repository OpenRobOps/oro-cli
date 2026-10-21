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

import difflib
import glob
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import NoReturn

import click
import yaml
from tabulate import tabulate
from unidiff import PatchSet

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


# --- apply -----------------------------------------------------------------


def resolve_paths(path: str) -> list[str]:
    if os.path.isfile(path):
        return [path]
    files = []
    for pattern in ("**/*.yaml", "**/*.yml", "**/*.json"):
        files.extend(glob.glob(os.path.join(path, pattern), recursive=True))
    return sorted(files)


def load_configs(filename: str) -> list[dict]:
    """Loads config objects from a YAML (multi-document) or JSON file."""
    with open(filename) as fd:
        docs = [d for d in yaml.safe_load_all(fd) if d is not None]
    if len(docs) == 1 and isinstance(docs[0], list):
        docs = docs[0]
    return [d for d in docs if isinstance(d, dict)]


def drop_scope(config_object: dict, source: str) -> None:
    metadata = config_object.get("metadata") or {}
    if "scope" in metadata:
        click.echo(
            f"warning: ignoring metadata.scope in {config_object.get('kind')}/{metadata.get('id')}"
            f" ({source}) - not used by ORO",
            err=True,
        )
        del metadata["scope"]


def display_config_diff(current: dict | None, new: dict) -> None:
    click.echo("----------")
    click.echo(f"Showing diff for {new.get('kind')}: {new.get('metadata', {}).get('id')}")
    old_lines = yaml.safe_dump(current or {}, sort_keys=True).splitlines(keepends=True)
    new_lines = yaml.safe_dump(new, sort_keys=True).splitlines(keepends=True)
    diff_text = "".join(
        difflib.unified_diff(old_lines, new_lines, fromfile="current.yaml", tofile="new.yaml")
    )
    if not diff_text:
        click.echo("No diffs detected.")
        return
    for patched_file in PatchSet(diff_text):
        for hunk in patched_file:
            for line in hunk:
                src = line.source_line_no or ""
                tgt = line.target_line_no or ""
                value = line.value.rstrip("\n")
                if line.is_context:
                    click.echo(f"{src:>4} {tgt:>4} |   {value}")
                elif line.is_removed and current:
                    click.echo(click.style(f"{src:>4}      | - {value}", fg="red"))
                elif line.is_added:
                    click.echo(click.style(f"{tgt:>4}      | + {value}", fg="green"))


def display_response_messages(response, index: int | None = None) -> None:
    try:
        messages = response.json().get("messages") or []
    except (ValueError, AttributeError):
        return
    colors = {"warn": "yellow", "error": "red"}
    for m in messages:
        message = m.get("message") if isinstance(m, dict) else m
        level = (m.get("level") or "").lower() if isinstance(m, dict) else ""
        if message:
            prefix = f"[{index}] " if index is not None else ""
            click.echo(prefix + click.style(message, fg=colors.get(level)))


@cli.command("apply")
@click.option("-f", "path", required=True, type=click.Path(exists=True, resolve_path=True))
@click.option("-y", "yes", is_flag=True, help="Apply without asking for confirmation.")
@click.option("--compare", is_flag=True, help="Only show differences, do not apply.")
@click.option(
    "--all", "include_all", is_flag=True, help="Also report server configs missing locally."
)
@click.option(
    "--exclude", "exclude_kinds", multiple=True, help="Kind to exclude (with --all). Repeatable."
)
def apply_config(
    path: str, yes: bool, compare: bool, include_all: bool, exclude_kinds: tuple[str, ...]
) -> None:
    """Apply configuration from a file or directory, showing a diff first."""
    if exclude_kinds and not include_all:
        raise click.UsageError("--exclude requires --all")
    objects = [(obj, file) for file in resolve_paths(path) for obj in load_configs(file)]
    if include_all:
        kinds = [k for k in list_kinds() if k not in exclude_kinds]
    else:
        kinds = sorted({o.get("kind") for o, _ in objects if o.get("kind")} - set(exclude_kinds))
    current: dict[str, dict[str, dict]] = {}
    for kind in kinds:
        try:
            items = list_configs(kind, full=True, include_all=True)
        except OroError as e:
            if e.status == 401:
                click.echo(f"warning: unauthorized for kind {kind}, skipping", err=True)
                continue
            fail(e)
        current[kind] = {i["metadata"]["id"]: i for i in items if i.get("metadata", {}).get("id")}
    local_ids: dict[str, set[str]] = defaultdict(set)
    for index, (obj, source) in enumerate(objects):
        kind = obj.get("kind")
        config_id = (obj.get("metadata") or {}).get("id")
        if not kind or not config_id:
            logger.debug("Skipping entry in %s: missing kind or metadata.id", source)
            continue
        if kind not in current:
            logger.debug("Skipping %s/%s: kind not available", kind, config_id)
            continue
        drop_scope(obj, source)
        local_ids[kind].add(config_id)
        display_config_diff(current[kind].get(config_id), obj)
        if compare:
            click.echo("Comparison finished")
            continue
        if not yes and not click.confirm("Do you want to apply this configuration?"):
            continue
        try:
            response = get_client().http_post("configuration/apply", obj)
        except OroError as e:
            fail(e)
        display_response_messages(response, index)
        click.echo(f"Configuration from {source} for {kind} {config_id} applied successfully.")
    if include_all:
        for kind, items in current.items():
            for missing in sorted(set(items) - local_ids[kind]):
                click.echo(f"Missing {kind} config: {missing}")
