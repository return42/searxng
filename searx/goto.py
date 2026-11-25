# SPDX-License-Identifier: AGPL-3.0-or-later
"""Redirect proxy for GOTO url"""

import typing as t
import hashlib
import hmac
import time
from urllib.parse import urljoin, urlsplit

import msgspec
import flask
from curl_cffi.requests.exceptions import RequestException

from searx import get_setting
from searx.extended_types import sxng_request
from searx.network import get  # see https://github.com/searxng/searxng/issues/762

app = flask.Blueprint("goto", __name__)
"""Blueprint for the /goto endpoint."""

token_encoder = msgspec.json.Encoder(order="sorted")

MethodT = t.Literal["proxy_redirects"]
"""Method that determines how the GOTO URL is to be handled.

proxy_redirects:
  The HTTP redirect response of the cloaked URL is passed upstream.
"""

Methods: tuple[str] = t.get_args(MethodT)
"""List of GOTO method names."""


class GotoURL(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """URL that must be handled by a redirect proxy (EP: ``/goto``)"""

    url: str
    """GOTO url (cloaking scheme)"""

    link: str = ""
    """Alternative URL that should be displayed to the user as long as the real
    URL is not yet known."""

    method: MethodT = "proxy_redirects"
    """Method that determines how the GOTO URL is to be handled."""

    token: str = ""
    """The token is built at the time of the instantiation of the class and is
    valid from then on for 60 minutes."""

    expires: int = msgspec.field(default_factory=lambda: int(time.time()) + 3600)
    """Time from which the proxy URL becomes invalid."""

    def __post_init__(self) -> None:
        if not self.token:
            self.token = self._token()
        if self.method not in Methods:
            raise ValueError(f"GotoURL.method named {self.method} is unknown")
        _ = urlsplit(self.url)  # will raise a ValueError if url is invalid

    def _token(self) -> str:
        secret: bytes = get_setting("server.secret_key").encode("utf-8")  # type: ignore
        fields: dict[str, t.Any] = msgspec.to_builtins(self)  # pyright: ignore[reportAny]
        del fields["token"]
        return hmac.new(secret, token_encoder.encode(fields), hashlib.sha256).hexdigest()

    @property
    def token_is_valid(self) -> bool:
        return hmac.compare_digest(
            self.token.encode("utf-8"),
            self._token().encode("ascii"),
        )

    @property
    def has_expired(self) -> bool:
        return time.time() >= self.expires

    def proxy_url(self) -> str:
        """Generates the URL for the GOTO proxy endpoint."""
        data = msgspec.json.encode(self).decode("utf-8")
        return flask.url_for("searx.goto.goto", data=data, _external=True)

    @classmethod
    def from_payload(cls, payload: bytes) -> "GotoURL" | tuple[flask.Response, int]:

        # pylint: disable=too-many-return-statements
        if size := len(payload) > 8192:
            return flask.jsonify(error=f"GotoURL: payload - exceeds maximum size ({size})"), 413
        try:
            raw = msgspec.json.decode(payload)  # pyright: ignore[reportAny]
        except msgspec.DecodeError:
            return flask.jsonify(error="GotoURL: payload - can't decode"), 400

        # There must be a token in the payload, otherwise GotoURL.__post_init__
        # will create a valid token by default and we can no longer test the
        # validity of token (from the payload).

        token = raw.get("token")  # pyright: ignore[reportAny]
        if not (isinstance(token, str) and token):
            return flask.jsonify(error="GotoURL: payload - missing or invalid 'token'"), 400

        # factory build incl. data type validation
        try:
            goto_url = msgspec.convert(raw, type=GotoURL)
        except msgspec.ValidationError as exc:
            return flask.jsonify(error=f"GotoURL: payload - ValidationError {exc}"), 400

        if not goto_url.token_is_valid:
            return flask.jsonify(error="GotoURL: token - isn't valid"), 403

        if goto_url.has_expired:
            return flask.jsonify(error="GotoURL: token - has been expired"), 403

        return goto_url


def proxy_redirects(goto_url: GotoURL) -> flask.Response | tuple[flask.Response, int]:
    g = urlsplit(goto_url.url)
    if g.scheme not in ("http", "https"):
        return flask.jsonify(error=f"GotoURL: proxy_redirects - cant handle {g.scheme}"), 400
    try:
        resp = get(
            goto_url.url,
            # pass redirect upstream, don't follow
            allow_redirects=False,
            # don't load the response body (all we need is status and location)
            stream=True,
            timeout=60,
        )
        location: str = resp.headers.get("Location") or ""
        status = resp.status_code
        # don't load the response body, close!
        resp.close()
    except RequestException as exc:
        return flask.jsonify(error=f"GotoURL: proxy_redirects - {exc}"), 400

    if not (status in (301, 302, 303, 307, 308) and location):
        return flask.jsonify(error=f"HTTP status {status} from {g.hostname}"), 502

    upstream = flask.Response(status=resp.status_code)
    upstream.headers["Location"] = urljoin(goto_url.url, location)
    return upstream


@app.route("/goto", methods=["GET", "POST"])
def goto() -> flask.Response | tuple[flask.Response, int]:

    if sxng_request.method == "GET":
        values = sxng_request.args.getlist("data")
        if len(values) != 1:
            return flask.jsonify(error="invalid data URL"), 400
        payload = values[0].encode("utf-8")

    else:
        payload = sxng_request.get_data()

    obj = GotoURL.from_payload(payload)
    if not isinstance(obj, GotoURL):
        return obj

    match obj.method:
        case "proxy_redirects":
            upstream = proxy_redirects(obj)
        case _:  # pyright: ignore[reportUnnecessaryComparison]
            upstream = (
                # pyright: ignore[reportUnreachable]
                flask.jsonify(error=f"can't handle goto method {obj.method}"),
                400,
            )

    return upstream
