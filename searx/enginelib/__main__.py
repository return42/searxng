"""Implementation of a command line for development purposes.  To start a
command, switch to the environment and run library module as a script::

   $ ./manage dev.env
   (dev.env)$ python -m searx.enginelib --help

The following commands can be used for maintenance and introspection
(development) of the engine cache::

   (dev.env)$ python -m searx.enginelib cache state
   (dev.env)$ python -m searx.enginelib cache maintenance

"""

import typer

from .. import enginelib
from . import sessions

app = typer.Typer()
app.add_typer(enginelib.app, name="cache", help="Commands related to the cache of the engines.")
app.add_typer(sessions.cli, name="sidecar", help="Commands related to the sessions of the engines.")
app()
