"""Digi-Key OAuth2 token handling."""

import json
import logging
import os
import ssl
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from json.decoder import JSONDecodeError
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from webbrowser import open_new

import requests
from certauth.certauth import CertificateAuthority

from digikey.constants import USER_AGENT
from digikey.exceptions import DigikeyOauthError

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

CA_CERT = "digikey-api.pem"
TOKEN_STORAGE = "token_storage.json"
TOKEN_LOCK = "token_storage.lock"
TOKEN_EXPIRY_MARGIN_SECONDS = 60

_TRUTHY_ENV = {"1", "true", "yes", "on"}
_PROCESS_TOKEN_LOCKS: dict[str, threading.Lock] = {}
_PROCESS_TOKEN_LOCKS_GUARD = threading.Lock()

AUTH_URL_V3_PROD = "https://api.digikey.com/v1/oauth2/authorize"
TOKEN_URL_V3_PROD = "https://api.digikey.com/v1/oauth2/token"

AUTH_URL_V3_SB = "https://sandbox-api.digikey.com/v1/oauth2/authorize"
TOKEN_URL_V3_SB = "https://sandbox-api.digikey.com/v1/oauth2/token"

REDIRECT_URI = "https://localhost:8139/digikey_callback"
PORT = 8139

logger = logging.getLogger(__name__)


def _env_flag(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY_ENV


def use_local_tool(enabled: bool = True) -> None:
    """
    Skip browser verification and request tokens with client credentials.

    Enable this when the library runs as a local tool. The client id and secret
    are exchanged for an access token, and parallel callers share that request
    instead of each starting a browser login.

    The flag is read when a token is requested, so call this before the API.
    ``DIGIKEY_LOCAL_TOOL=1`` and ``DIGIKEY_NO_BROWSER=1`` enable the same mode.
    """
    os.environ["DIGIKEY_LOCAL_TOOL"] = "1" if enabled else "0"


def _process_token_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _PROCESS_TOKEN_LOCKS_GUARD:
        lock = _PROCESS_TOKEN_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PROCESS_TOKEN_LOCKS[key] = lock
        return lock


class _FileLock:
    """Exclusive lock so separate processes share one token request."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle = None

    def __enter__(self) -> "_FileLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._path.open("a+")
        if fcntl is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: object,
    ) -> None:
        if self._handle is None:
            return
        if fcntl is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None


class Oauth2Token:
    def __init__(self, token) -> None:
        self._token = token

    @property
    def access_token(self):
        return self._token.get("access_token")

    @property
    def refresh_token(self):
        return self._token.get("refresh_token")

    @property
    def expires(self):
        return datetime.fromtimestamp(self._token.get("expires"), timezone.utc)

    @property
    def type(self):
        return self._token.get("token_type") or "Bearer"

    def expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires

    def get_authorization(self) -> str:
        return self.type + " " + self.access_token

    def __repr__(self) -> str:
        return f"<Token: expires={self.expires.astimezone().isoformat()}>"


class HTTPServerHandler(BaseHTTPRequestHandler):
    """HTTP Server callbacks to handle Digikey OAuth redirects"""

    def __init__(self, request, address, server, a_id, a_secret) -> None:
        self.app_id = a_id
        self.app_secret = a_secret
        self.auth_code = None
        super().__init__(request, address, server)

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        get_params = parse_qs(urlparse(self.path).query)
        if "code" in get_params:
            self.auth_code = get_params["code"][0]
            self.wfile.write(
                bytes(
                    "<html>" + "<body>"
                    "<h1>You may now close this window.</h1>"
                    + "<p>Auth code retreived: "
                    + self.auth_code
                    + "</p>"
                    "</body>"
                    "</html>",
                    "utf-8",
                )
            )
            self.server.auth_code = self.auth_code
            self.server.stop = 1
        else:
            raise DigikeyOauthError(
                f"Digikey did not return authorization token in request: {self.path}"
            )

    # Disable logging from the HTTP Server
    def log_message(self, format, *args) -> None:
        return


class TokenHandler:
    """
    Functions used to handle Digikey oAuth.

    Set ``interactive`` to False, call :func:`use_local_tool`, or export
    ``DIGIKEY_LOCAL_TOOL=1`` to request a token with the client id and secret
    and skip browser verification. Token reads and writes are locked so
    parallel processes share one request.
    """

    def __init__(  # noqa: PLR0913
        self,
        a_id: str | None = None,
        a_secret: str | None = None,
        a_token_storage_path: str | None = None,
        version: int = 2,
        sandbox: bool = False,
        interactive: bool | None = None,
    ) -> None:
        if version in {3, 4}:
            if sandbox:
                self.auth_url = AUTH_URL_V3_SB
                self.token_url = TOKEN_URL_V3_SB
            else:
                self.auth_url = AUTH_URL_V3_PROD
                self.token_url = TOKEN_URL_V3_PROD
        else:
            raise ValueError("Please specify the correct Digikey API version")

        logger.debug(f"Using API V{version}")

        a_id = a_id or os.getenv("DIGIKEY_CLIENT_ID")
        a_secret = a_secret or os.getenv("DIGIKEY_CLIENT_SECRET")
        if not a_id or not a_secret:
            raise ValueError(
                "CLIENT ID and SECRET must be set. "
                'Set "DIGIKEY_CLIENT_ID" and "DIGIKEY_CLIENT_SECRET" '
                "as an environment variable, or pass your keys directly to the client."
            )

        a_token_storage_path = a_token_storage_path or os.getenv("DIGIKEY_STORAGE_PATH")
        if not a_token_storage_path or not Path(a_token_storage_path).exists():
            raise ValueError(
                "STORAGE PATH must be set and must exist."
                'Set "DIGIKEY_STORAGE_PATH" as an environment variable, '
                "or pass your keys directly to the client."
            )

        self._id = a_id
        self._secret = a_secret
        self._storage_path = Path(a_token_storage_path)
        self._token_storage_path = self._storage_path.joinpath(TOKEN_STORAGE)
        self._lock_path = self._storage_path.joinpath(TOKEN_LOCK)
        self._ca_cert = self._storage_path.joinpath(CA_CERT)
        self._interactive_override = interactive

    @property
    def interactive(self) -> bool:
        """Return False when browser verification must be skipped."""
        if self._interactive_override is not None:
            return self._interactive_override
        return not (_env_flag("DIGIKEY_NO_BROWSER") or _env_flag("DIGIKEY_LOCAL_TOOL"))

    def __generate_certificate(self):
        ca = CertificateAuthority(
            "Python digikey-api CA",
            str(self._ca_cert),
            cert_cache=str(self._storage_path),
        )
        return ca.cert_for_host("localhost")

    def __build_authorization_url(self) -> str:
        params = {
            "client_id": self._id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
        }
        url = self.auth_url + "?" + urlencode(params)
        logger.debug(
            f"AUTH - Authenticating with endpoint {self.auth_url} using ID: {self._id[:-5]}..."
        )
        logger.debug(f"AUTH - Redirect URL: {REDIRECT_URI}")
        return url

    def __exchange_for_token(self, code):
        headers = {
            "user-agent": USER_AGENT,
            "Content-type": "application/x-www-form-urlencoded",
        }
        post_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self._id,
            "client_secret": self._secret,
            "redirect_uri": REDIRECT_URI,
        }

        try:
            logger.debug(
                f"TOKEN - Exchanging {code} auth code for token at endpoint: {self.token_url}"
            )
            logger.debug(f"TOKEN - Using client id: {self._id[:-5]}...")
            logger.debug(f"TOKEN - Using client secret: {self._secret[:-5]}...")
            r = requests.post(self.token_url, headers=headers, data=post_data)
            r.raise_for_status()
        except (
            requests.exceptions.RequestException,
            requests.exceptions.HTTPError,
        ) as e:
            raise DigikeyOauthError(
                f"TOKEN - Cannot request new token with auth code: {e}"
            )
        else:
            token_json = r.json()
            logger.debug(
                f"TOKEN - Got access token with value: {token_json['access_token'][:-5]}..."
            )
            logger.info("TOKEN - Successfully retrieved access token.")

        return self._stamp_token(token_json, "authorization_code")

    def __refresh_token(self, refresh_token: str):
        headers = {
            "user-agent": USER_AGENT,
            "Content-type": "application/x-www-form-urlencoded",
        }
        post_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._id,
            "client_secret": self._secret,
        }
        error_message = None

        try:
            r = requests.post(self.token_url, headers=headers, data=post_data)
            error_message = r.json().get("error_description", None)
            r.raise_for_status()
        except (
            requests.exceptions.RequestException,
            requests.exceptions.HTTPError,
        ):
            raise DigikeyOauthError(
                f"REFRESH - Cannot request new token with refresh token: {error_message}."
            )
        else:
            token_json = r.json()
            logger.debug(f"REFRESH - Got access token with value: {token_json['access_token']}")
            logger.info("REFRESH - Successfully retrieved access token.")

        return self._stamp_token(token_json, "authorization_code")

    def _stamp_token(self, token_json: dict, grant_type: str) -> dict:
        try:
            expires_in = int(token_json["expires_in"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DigikeyOauthError(
                "TOKEN - Token response did not include a valid expires_in."
            ) from exc
        margin = (
            TOKEN_EXPIRY_MARGIN_SECONDS if expires_in > TOKEN_EXPIRY_MARGIN_SECONDS else 0
        )
        token_json["expires"] = expires_in + datetime.now(timezone.utc).timestamp() - margin
        token_json["grant_type"] = grant_type
        return token_json

    def _client_credentials_token(self) -> dict:
        """Exchange the client id and secret for an access token. No browser."""
        headers = {
            "user-agent": USER_AGENT,
            "Content-type": "application/x-www-form-urlencoded",
        }
        post_data = {
            "grant_type": "client_credentials",
            "client_id": self._id,
            "client_secret": self._secret,
        }
        error_message = None
        try:
            logger.debug(f"TOKEN - Requesting client-credentials token at {self.token_url}")
            response = requests.post(
                self.token_url, headers=headers, data=post_data, timeout=30
            )
            try:
                error_message = response.json().get("error_description")
            except ValueError:
                error_message = None
            response.raise_for_status()
            token_json = response.json()
        except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as exc:
            raise DigikeyOauthError(
                "TOKEN - Cannot request token with client credentials: "
                f"{error_message or exc}"
            ) from exc

        if not token_json.get("access_token"):
            raise DigikeyOauthError(
                "TOKEN - Client credentials response did not include an access token."
            )
        logger.info("TOKEN - Successfully retrieved access token with client credentials.")
        return self._stamp_token(token_json, "client_credentials")

    def _browser_token(self) -> dict:
        """Run the authorization-code flow in a browser and return a token."""
        open_new(self.__build_authorization_url())
        filename = self.__generate_certificate()
        httpd = HTTPServer(
            ("localhost", PORT),
            lambda request, address, server: HTTPServerHandler(
                request, address, server, self._id, self._secret
            ),
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(Path(filename)))
        httpd.socket = context.wrap_socket(
            httpd.socket,
            server_side=True,
        )
        httpd.stop = 0

        # This function will block until it receives a request
        while httpd.stop == 0:
            httpd.handle_request()
        httpd.server_close()

        # Remove generated certificate
        try:
            os.remove(Path(filename))
            os.remove(self._ca_cert)
        except OSError:
            logger.exception("Cannot remove temporary certificates")

        return self.__exchange_for_token(httpd.auth_code)

    def _read_stored_token(self) -> dict | None:
        try:
            with self._token_storage_path.open() as handle:
                token_json = json.load(handle)
        except (OSError, JSONDecodeError):
            logger.warning("Oauth2 token storage does not exist or malformed, creating new.")
            return None
        if not isinstance(token_json, dict):
            logger.warning("Oauth2 token storage is malformed, creating new.")
            return None
        return token_json

    def _token_from_storage(self, token_json: dict | None) -> Oauth2Token | None:
        if not token_json:
            return None
        if not token_json.get("access_token") or token_json.get("expires") is None:
            logger.warning("Oauth2 token storage is malformed, creating new.")
            return None
        try:
            return Oauth2Token(token_json)
        except (TypeError, ValueError, OSError):
            logger.warning("Oauth2 token storage is malformed, creating new.")
            return None

    def _obtain_new_token(self, previous: dict | None) -> dict:
        previous_grant = previous.get("grant_type") if previous else None
        if previous_grant == "client_credentials" or not self.interactive:
            if not self.interactive and previous is None:
                logger.info(
                    "AUTH - Local tool mode: requesting an access token from the "
                    "client id and secret. Browser verification is skipped."
                )
            else:
                logger.debug("TOKEN - Requesting a client-credentials access token.")
            return self._client_credentials_token()
        logger.info("AUTH - Starting browser authorization.")
        return self._browser_token()

    def _get_access_token_locked(self) -> Oauth2Token:
        token_json = self._read_stored_token()
        token = self._token_from_storage(token_json)

        if token is not None and not token.expired():
            return token

        if (
            token is not None
            and token.refresh_token
            and (token_json or {}).get("grant_type") != "client_credentials"
        ):
            try:
                logger.debug("REFRESH - Current token is stale, refreshing stored credentials.")
                token_json = self.__refresh_token(token.refresh_token)
            except DigikeyOauthError:
                logger.exception(
                    "REFRESH - Failed to use refresh token, requesting a new access token."
                )
                token_json = self._obtain_new_token(token_json)
        else:
            token_json = self._obtain_new_token(None if token is None else token_json)

        self.save(token_json)
        return Oauth2Token(token_json)

    def save(self, json_data: dict) -> None:
        """Write the token JSON to the storage path."""
        with self._token_storage_path.open("w") as handle:
            json.dump(json_data, handle)
            logger.debug(f"Saved token to: {self._token_storage_path}")

    def get_access_token(self) -> Oauth2Token:
        """
        Return a cached access token, refreshing or requesting one if needed.

        Local-tool mode requests the token with client credentials and does not
        open a browser. Callers in this process and in other processes share
        one token request, so a missing token does not start a login per caller.
        """
        thread_lock = _process_token_lock(self._token_storage_path)
        with thread_lock, _FileLock(self._lock_path):
            return self._get_access_token_locked()
