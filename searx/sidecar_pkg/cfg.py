# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!!   [POC:SideCar]"""
# pylint: disable=too-few-public-methods


class CFG:
    """SideCar's config"""

    # SideCar's WEB server, in the [POC:SideCar] we use:
    #
    #   (dev.env)$ python -m searx.sidecar_pkg web --help

    SIDECAR_LISTEN: tuple[str, int] = "127.0.0.2", 50000
    """Host and port SearXNG's sidecar server listens on."""

    SIDECAR_URL: str = f"http://127.0.0.2:{SIDECAR_LISTEN[1]}"
    """Base URL for requests to SearXNG's sidecar server."""

    # Remote SearXNG instance, in the [POC:SideCar] we use the development
    # server:
    #
    #   $ make run

    SXNG_URL: str = "http://127.0.0.1:8888/sidecar"
    """URL (endpoint) for accessing the sidecar functions on the (remote)
    SearXNG instance."""

    SXNG_AUTH_TOKEN: str = "123"
    """Authentication token for the remote SearXNG instance.

    ToDo: auth needs more work!!
    """

    SOCKS5: str = ""  # "127.0.0.1:8080"
    """With a `SSH tunnel`_ we can send requests from server’s IP::

      # SOCKS server: socks://127.0.0.1:8080
      $ ssh -q -N -D 8080 user@example.org

    .. _SSH tunnel: https://docs.searxng.org/admin/answer-captcha.html
    """
