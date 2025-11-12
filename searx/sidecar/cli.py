# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!!   [POC:SideCar]

Implementation of a command line for SideCar's tools & services within a running
SearXNG instance.

In this POC, to use this command line, first jump into SerXNG's
developer environment:

    $ ./manage dev.env

To get an overview of available commands:

    (dev.env)$ python -m searx.sidecar --help

"""

import typer

from .cache import CACHE

CLI = typer.Typer()
_CACHE = typer.Typer()
CLI.add_typer(_CACHE, name="cache", help="Commands related to the cache of the engines.")


@_CACHE.command()
def state():
    """Show state for the SideCar's caches."""

    title = "cache tables and key/values"
    print(title)
    print("=" * len(title))
    print(CACHE.state().report())
    print()
    title = f"properties of {CACHE.cfg.name}"
    print(title)
    print("=" * len(title))
    print(str(CACHE.properties))


@_CACHE.command()
def clear():
    """Clears SideCar's caches."""
    CACHE.maintenance(force=True, truncate=True)
