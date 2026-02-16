# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "typer>=0.15",
#     "rich>=13",
#     "httpx>=0.27",
#     "jinja2>=3",
#     "python-dotenv>=1",
# ]
# ///

"""zpod-template-generator: Render Jinja2 templates with zPod metadata from zpodapi."""

from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path
from typing import Annotated, Optional

import httpx
import typer
from dotenv import load_dotenv
import jinja2
from jinja2 import Environment, FileSystemLoader, TemplateError
from rich.console import Console

load_dotenv()

app = typer.Typer(
    name="zpod-template-generator",
    help="Render Jinja2 templates with zPod metadata from the zpodapi.",
    add_completion=False,
)

err_console = Console(stderr=True)


def _sanitize_component_name(name: str) -> str:
    """Convert a component name to a valid Python identifier for template use."""
    return re.sub(r"[^a-zA-Z0-9]", "_", name).strip("_").lower()


def _fetch_zpod(host: str, token: str, zpod_name: str) -> dict:
    """Fetch zpod details by name from the zpodapi."""
    url = f"{host.rstrip('/')}/zpods/name={zpod_name}"
    headers = {"access_token": token}

    try:
        response = httpx.get(url, headers=headers, timeout=30)
    except httpx.ConnectError:
        err_console.print(f"[red]Error:[/red] Cannot connect to zpodapi at {host}")
        raise typer.Exit(code=1)
    except httpx.RequestError as exc:
        err_console.print(f"[red]Error:[/red] Request failed: {exc}")
        raise typer.Exit(code=1)

    if response.status_code == 401:
        err_console.print("[red]Error:[/red] Authentication failed. Check your API token.")
        raise typer.Exit(code=1)
    if response.status_code == 404:
        err_console.print(f"[red]Error:[/red] zPod '{zpod_name}' not found.")
        raise typer.Exit(code=1)
    if response.status_code != 200:
        err_console.print(
            f"[red]Error:[/red] API returned status {response.status_code}: {response.text}"
        )
        raise typer.Exit(code=1)

    return response.json()


def _fetch_zpods(host: str, token: str) -> list[dict]:
    """Fetch all zpods from the zpodapi."""
    url = f"{host.rstrip('/')}/zpods"
    headers = {"access_token": token}

    try:
        response = httpx.get(url, headers=headers, timeout=30)
    except httpx.ConnectError:
        err_console.print(f"[red]Error:[/red] Cannot connect to zpodapi at {host}")
        raise typer.Exit(code=1)
    except httpx.RequestError as exc:
        err_console.print(f"[red]Error:[/red] Request failed: {exc}")
        raise typer.Exit(code=1)

    if response.status_code == 401:
        err_console.print("[red]Error:[/red] Authentication failed. Check your API token.")
        raise typer.Exit(code=1)
    if response.status_code != 200:
        err_console.print(
            f"[red]Error:[/red] API returned status {response.status_code}: {response.text}"
        )
        raise typer.Exit(code=1)

    return response.json()


def _fetch_zpod_dns_records(host: str, token: str, zpod_id: int) -> list[dict]:
    """Fetch DNS entries for a zpod."""
    url = f"{host.rstrip('/')}/zpods/{zpod_id}/dns"
    headers = {"access_token": token}

    try:
        response = httpx.get(url, headers=headers, timeout=30)
    except httpx.RequestError as exc:
        err_console.print(f"[yellow]Warning:[/yellow] Failed to fetch DNS entries: {exc}")
        return []

    if response.status_code != 200:
        err_console.print(
            f"[yellow]Warning:[/yellow] Could not fetch DNS entries (status {response.status_code})"
        )
        return []

    return response.json()


def _fetch_settings(host: str, token: str) -> list[dict]:
    """Fetch all zPodFactory settings."""
    url = f"{host.rstrip('/')}/settings"
    headers = {"access_token": token}

    try:
        response = httpx.get(url, headers=headers, timeout=30)
    except httpx.RequestError as exc:
        err_console.print(f"[yellow]Warning:[/yellow] Failed to fetch settings: {exc}")
        return []

    if response.status_code != 200:
        err_console.print(
            f"[yellow]Warning:[/yellow] Could not fetch settings (status {response.status_code})"
        )
        return []

    return response.json()


def _build_template_context(zpod: dict, zpod_dns_records: list[dict], settings: list[dict], extra_vars: dict | None) -> dict:
    """Build the template context dict from zpod data and extra variables."""
    context = {
        # Root zpod fields
        "zpod_id": zpod.get("id"),
        "zpod_name": zpod.get("name"),
        "zpod_description": zpod.get("description"),
        "zpod_domain": zpod.get("domain"),
        "zpod_password": zpod.get("password"),
        "zpod_profile": zpod.get("profile"),
        "zpod_status": zpod.get("status"),
        "zpod_creation_date": zpod.get("creation_date"),
        "zpod_last_modified_date": zpod.get("last_modified_date"),
        # Full objects for iteration
        "zpod_components": zpod.get("components", []),
        "zpod_networks": zpod.get("networks", []),
        "zpod_dns_records": zpod_dns_records,
        "zpod_endpoint": zpod.get("endpoint"),
        "zpod_features": zpod.get("features"),
        "zpod_permissions": zpod.get("permissions", []),
        # Settings
        "zpod_settings": settings,
    }

    # Convenience: individual settings by name -> value
    settings_by_name = {}
    for setting in settings:
        setting_name = setting.get("name", "")
        if setting_name:
            key = f"zpod_setting_{_sanitize_component_name(setting_name)}"
            context[key] = setting.get("value")
            settings_by_name[setting_name] = setting.get("value")

    # Computed network values from the first (management) network
    networks = zpod.get("networks", [])
    if networks:
        try:
            mgmt_network = ipaddress.ip_network(networks[0].get("cidr", ""), strict=False)
            # Gateway is the first usable host (.1) in the management network
            network_addr = str(mgmt_network.network_address)
            context["zpod_subnet"] = network_addr.rsplit(".", 1)[0]
            context["zpod_gateway"] = str(mgmt_network.network_address + 1)
            context["zpod_netmask"] = str(mgmt_network.netmask)
            context["zpod_netprefix"] = mgmt_network.prefixlen
        except ValueError:
            pass

    # Convenience: individual components by name
    zbox_ip = None
    for comp in zpod.get("components", []):
        comp_info = comp.get("component", {})
        comp_name = comp_info.get("component_name", "")
        if comp_name:
            key = f"zpod_component_{_sanitize_component_name(comp_name)}"
            context[key] = comp
            if comp_name == "zbox":
                zbox_ip = comp.get("ip")

    # Computed infrastructure values
    context["zpod_portgroup"] = f"zpod-{zpod['name']}-segment"
    context["zpod_dns"] = zbox_ip
    context["zpod_nfs"] = zbox_ip
    context["zpod_ntp"] = settings_by_name.get("zpodfactory_host")
    context["zpod_sshkey"] = settings_by_name.get("zpodfactory_ssh_key")

    # Extra variables from JSON file (keys used as-is, no prefix)
    if extra_vars:
        context.update(extra_vars)

    return context


@app.command()
def generate(
    zpodfactory_host: Annotated[
        str,
        typer.Option(
            "--zpodfactory-host",
            envvar="ZPODFACTORY_HOST",
            help="zpodapi host URL (e.g. http://zpodfactory.fqdn.com:8000)",
        ),
    ],
    zpodfactory_token: Annotated[
        str,
        typer.Option(
            "--zpodfactory-token",
            envvar="ZPODFACTORY_TOKEN",
            help="zpodapi access token",
        ),
    ],
    list_zpods: Annotated[
        bool,
        typer.Option(
            "--list-zpods",
            help="List available zPods and exit",
        ),
    ] = False,
    zpod_name: Annotated[
        Optional[str],
        typer.Option(
            "--zpod-name",
            help="Name of the zPod to fetch",
        ),
    ] = None,
    template_file: Annotated[
        Optional[Path],
        typer.Option(
            "--template-file",
            help="Path to the Jinja2 template file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    template_extra_vars: Annotated[
        Optional[Path],
        typer.Option(
            "--extra-vars",
            help="Path to a JSON file with extra template variables",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    output_file: Annotated[
        Optional[Path],
        typer.Option(
            "--output-file",
            help="Write rendered output to file instead of stdout",
        ),
    ] = None,
) -> None:
    """Fetch zPod metadata and render a Jinja2 template."""
    # List zpods mode
    if list_zpods:
        zpods = _fetch_zpods(zpodfactory_host, zpodfactory_token)
        err_console.print("Available zPods:")
        for z in zpods:
            err_console.print(f"  - {z.get('name', '')}")
        raise typer.Exit()

    # Validate required options for generate mode
    if not zpod_name:
        err_console.print("[red]Error:[/red] --zpod-name is required for template generation.")
        raise typer.Exit(code=1)
    if not template_file:
        err_console.print("[red]Error:[/red] --template-file is required for template generation.")
        raise typer.Exit(code=1)

    # Load extra variables if provided
    extra_vars = None
    if template_extra_vars:
        try:
            extra_vars = json.loads(template_extra_vars.read_text())
        except json.JSONDecodeError as exc:
            err_console.print(
                f"[red]Error:[/red] Invalid JSON in extra vars file: {exc}"
            )
            raise typer.Exit(code=1)
        if not isinstance(extra_vars, dict):
            err_console.print(
                "[red]Error:[/red] Extra vars JSON must be an object (dict), "
                f"got {type(extra_vars).__name__}"
            )
            raise typer.Exit(code=1)

    # Fetch zpod data
    err_console.print(f"Fetching zPod '[bold]{zpod_name}[/bold]' from {zpodfactory_host}...")
    zpod = _fetch_zpod(zpodfactory_host, zpodfactory_token, zpod_name)

    zpod_id = zpod.get("id")
    err_console.print(f"Fetching DNS entries for zPod id={zpod_id}...")
    zpod_dns_records = _fetch_zpod_dns_records(zpodfactory_host, zpodfactory_token, zpod_id)

    err_console.print("Fetching zPodFactory settings...")
    settings = _fetch_settings(zpodfactory_host, zpodfactory_token)

    # Build template context
    context = _build_template_context(zpod, zpod_dns_records, settings, extra_vars)

    # Render template
    template_dir = str(template_file.parent.resolve())
    template_name = template_file.name
    env = Environment(
        loader=FileSystemLoader(template_dir),
        keep_trailing_newline=True,
        undefined=jinja2.Undefined,
    )

    try:
        template = env.get_template(template_name)
    except TemplateError as exc:
        err_console.print(f"[red]Error:[/red] Failed to load template: {exc}")
        raise typer.Exit(code=1)

    try:
        rendered = template.render(**context)
    except TemplateError as exc:
        err_console.print(f"[red]Error:[/red] Template rendering failed: {exc}")
        raise typer.Exit(code=1)

    # Output
    if output_file:
        output_file.write_text(rendered)
        err_console.print(f"[green]Output written to {output_file}[/green]")
    else:
        print(rendered)


if __name__ == "__main__":
    app()
