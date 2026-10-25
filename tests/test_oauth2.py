import logging
import os
import re
import ssl
import json
import sys
import tempfile
import time
import unittest
import urllib.request
import urllib.parse as urlparse
from json.decoder import JSONDecodeError
from unittest import TestCase
import unittest.mock as mock
from pathlib import Path
from datetime import datetime, timezone
import threading

import requests

import responses

from digikey.exceptions import DigikeyOauthError
from digikey.oauth import oauth2
from . import fixtures

logger = logging.getLogger(__name__)
logger.level = logging.DEBUG


def mock_open_new(url):
    parsed = urlparse.parse_qs(urlparse.urlparse(url).query)
    assert parsed['client_id'][0] == 'MOCK_CLIENT_ID'
    assert parsed['redirect_uri'][0] == 'https://localhost:8139/digikey_callback'

    # Call the redirect URI
    values = {'code': 'MOCK_AUTH_CODE'}
    data = urllib.parse.urlencode(values)
    req = parsed['redirect_uri'][0] + '?' + data
    threading.Thread(target=lambda: urllib.request.urlopen(req, context=ssl._create_unverified_context())).start()
    pass


class Oauth2Tests(TestCase):
    def setUp(self):
        self.old_token_storage_path = os.getenv('DIGIKEY_STORAGE_PATH', "")
        self.old_client_id = os.getenv('DIGIKEY_CLIENT_ID', "")
        self.old_client_secret = os.getenv('DIGIKEY_CLIENT_SECRET', "")

        os.environ['DIGIKEY_STORAGE_PATH'] = str(Path(__file__).parent)
        os.environ['DIGIKEY_CLIENT_ID'] = 'MOCK_CLIENT_ID'
        os.environ['DIGIKEY_CLIENT_SECRET'] = 'MOCK_CLIENT_SECRET'

        self.stream_handler = logging.StreamHandler(sys.stdout)
        logger.addHandler(self.stream_handler)

    def tearDown(self):
        os.environ['DIGIKEY_STORAGE_PATH'] = self.old_token_storage_path
        os.environ['DIGIKEY_CLIENT_ID'] = self.old_client_id
        os.environ['DIGIKEY_CLIENT_SECRET'] = self.old_client_secret

        logger.removeHandler(self.stream_handler)

    @unittest.skip("Test hangs - needs investigation. The test references TOKEN_URL_V2 which no longer exists.")
    @responses.activate
    @mock.patch('digikey.oauth.oauth2.open_new', side_effect=mock_open_new)
    def test_authentication(self, mock_on):
        """Tests that token is retrieved correctly from authorization"""

        url_auth = re.compile(oauth2.TOKEN_URL_V3_PROD + r'.*')

        for version in [3]:
            logger.info(f'Tests that token is retrieved correctly from authorization [API V{version}]')

            # Mock out all calls to token endpoint.
            responses.add(
                responses.POST,
                url_auth,
                status=200,
                content_type='application/json',
                json=fixtures.oauth2_response
            )

            token = oauth2.TokenHandler(version=version).get_access_token()
            assert token.access_token == 'MOCK_ACCESS'
            assert token.refresh_token == 'MOCK_REFRESH'
            expires_in = (token.expires - datetime.now(timezone.utc)).seconds
            assert 86200 <= expires_in <= 86340

            token_file = Path(os.getenv('DIGIKEY_STORAGE_PATH', "")).joinpath(oauth2.TOKEN_STORAGE)
            cacert = Path(os.getenv('DIGIKEY_STORAGE_PATH', "")).joinpath(oauth2.CA_CERT)
            pemfile = Path(os.getenv('DIGIKEY_STORAGE_PATH', "")).joinpath('localhost.pem')

            # Test if temporary files have been cleaned up
            assert not cacert.is_file()
            assert not pemfile.is_file()

            # Test if token has been saved
            assert token_file.is_file()

            # Test for correct storage
            token_json = None
            try:
                with open(token_file, 'r') as f:
                    token_json = json.load(f)
            except (EnvironmentError, JSONDecodeError):
                print('Token storage does not exist or malformed')
                assert False

            os.remove(token_file)

            assert token_json['access_token'] == 'MOCK_ACCESS'
            assert token_json['refresh_token'] == 'MOCK_REFRESH'


def _token_response(payload, error=None):
    response = mock.Mock()
    response.json.return_value = payload
    if error is None:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = error
    return response


def _access_payload(access='MOCK_ACCESS', expires_in=599, refresh=None):
    payload = {
        'access_token': access,
        'expires_in': expires_in,
        'token_type': 'Bearer',
    }
    if refresh is not None:
        payload['refresh_token'] = refresh
    return payload


class FakeHTTPServer:
    """Stand-in for the localhost callback server used by the browser flow."""

    def __init__(self, address, handler) -> None:
        self.address = address
        self.handler = handler
        self.auth_code = 'MOCK_AUTH_CODE'
        self.stop = 0
        self.socket = mock.Mock()

    def handle_request(self) -> None:
        time.sleep(0.05)
        self.stop = 1

    def server_close(self) -> None:
        return None


class LocalToolOauthTests(TestCase):
    def setUp(self) -> None:
        self._old_local = os.environ.pop('DIGIKEY_LOCAL_TOOL', None)
        self._old_no_browser = os.environ.pop('DIGIKEY_NO_BROWSER', None)
        self._tmpdir = tempfile.TemporaryDirectory()
        self.storage = self._tmpdir.name

    def tearDown(self) -> None:
        self._tmpdir.cleanup()
        self._restore('DIGIKEY_LOCAL_TOOL', self._old_local)
        self._restore('DIGIKEY_NO_BROWSER', self._old_no_browser)

    @staticmethod
    def _restore(name, value) -> None:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    def _handler(self, **kwargs):
        params = {
            'a_id': 'MOCK_CLIENT_ID',
            'a_secret': 'MOCK_CLIENT_SECRET',
            'a_token_storage_path': self.storage,
            'version': 3,
        }
        params.update(kwargs)
        return oauth2.TokenHandler(**params)

    def _token_path(self) -> Path:
        return Path(self.storage).joinpath(oauth2.TOKEN_STORAGE)

    def test_local_tool_requests_client_credentials_without_browser(self) -> None:
        post = mock.Mock(return_value=_token_response(_access_payload()))
        with (
            mock.patch('digikey.oauth.oauth2.requests.post', post),
            mock.patch('digikey.oauth.oauth2.open_new', side_effect=AssertionError('browser')),
            mock.patch('digikey.oauth.oauth2.HTTPServer', side_effect=AssertionError('server')),
        ):
            token = self._handler(interactive=False).get_access_token()
            assert token.access_token == 'MOCK_ACCESS'
            assert token.get_authorization() == 'Bearer MOCK_ACCESS'
            cached = self._handler(interactive=False).get_access_token()

        assert cached.access_token == 'MOCK_ACCESS'
        posted = post.call_args.kwargs['data']
        assert posted['grant_type'] == 'client_credentials'
        assert posted['client_id'] == 'MOCK_CLIENT_ID'
        assert posted['client_secret'] == 'MOCK_CLIENT_SECRET'
        assert 'code' not in posted
        saved = json.loads(self._token_path().read_text())
        assert saved['grant_type'] == 'client_credentials'
        assert saved['access_token'] == 'MOCK_ACCESS'
        assert post.call_count == 1

    def test_use_local_tool_and_no_browser_env_skip_browser(self) -> None:
        post = mock.Mock(return_value=_token_response(_access_payload('ENV_TOKEN')))
        with (
            mock.patch('digikey.oauth.oauth2.requests.post', post),
            mock.patch('digikey.oauth.oauth2.open_new', side_effect=AssertionError('browser')),
        ):
            oauth2.use_local_tool()
            token = self._handler().get_access_token()
            assert token.access_token == 'ENV_TOKEN'

            os.environ['DIGIKEY_LOCAL_TOOL'] = '0'
            os.environ['DIGIKEY_NO_BROWSER'] = '1'
            self._token_path().unlink()
            token = self._handler().get_access_token()
            assert token.access_token == 'ENV_TOKEN'
        assert post.call_count == 2
        assert post.call_args.kwargs['data']['grant_type'] == 'client_credentials'

    def test_expired_client_credentials_token_is_renewed_without_browser(self) -> None:
        self._token_path().write_text(json.dumps({
            'access_token': 'OLD',
            'token_type': 'Bearer',
            'expires': datetime.now(timezone.utc).timestamp() - 10,
            'grant_type': 'client_credentials',
        }))
        post = mock.Mock(return_value=_token_response(_access_payload('NEW')))
        with (
            mock.patch('digikey.oauth.oauth2.requests.post', post),
            mock.patch('digikey.oauth.oauth2.open_new', side_effect=AssertionError('browser')),
        ):
            token = self._handler(interactive=True).get_access_token()
        assert token.access_token == 'NEW'
        assert post.call_count == 1
        assert post.call_args.kwargs['data']['grant_type'] == 'client_credentials'

    def test_failed_refresh_uses_client_credentials_in_local_mode(self) -> None:
        self._token_path().write_text(json.dumps({
            'access_token': 'OLD',
            'refresh_token': 'REFRESH',
            'token_type': 'Bearer',
            'expires': datetime.now(timezone.utc).timestamp() - 10,
            'grant_type': 'authorization_code',
        }))

        def side_effect(*_args, **kwargs):
            if kwargs['data']['grant_type'] == 'refresh_token':
                return _token_response(
                    {'error_description': 'expired'},
                    requests.HTTPError('400'),
                )
            return _token_response(_access_payload('NEW'))

        post = mock.Mock(side_effect=side_effect)
        with (
            mock.patch('digikey.oauth.oauth2.requests.post', post),
            mock.patch('digikey.oauth.oauth2.open_new', side_effect=AssertionError('browser')),
        ):
            token = self._handler(interactive=False).get_access_token()
        assert token.access_token == 'NEW'
        assert [call.kwargs['data']['grant_type'] for call in post.call_args_list] == [
            'refresh_token',
            'client_credentials',
        ]

    def test_client_credentials_failure_does_not_open_browser(self) -> None:
        response = _token_response(
            {'error_description': 'invalid client'},
            requests.HTTPError('401'),
        )
        with (
            mock.patch('digikey.oauth.oauth2.requests.post', return_value=response),
            mock.patch('digikey.oauth.oauth2.open_new', side_effect=AssertionError('browser')),
            self.assertRaises(DigikeyOauthError) as caught,
        ):
            self._handler(interactive=False).get_access_token()
        assert 'invalid client' in str(caught.exception)

    def test_valid_cached_token_is_reused(self) -> None:
        self._token_path().write_text(json.dumps({
            'access_token': 'CACHED',
            'refresh_token': 'REFRESH',
            'token_type': 'Bearer',
            'expires': datetime.now(timezone.utc).timestamp() + 3600,
            'grant_type': 'authorization_code',
        }))
        post = mock.Mock()
        with (
            mock.patch('digikey.oauth.oauth2.requests.post', post),
            mock.patch('digikey.oauth.oauth2.open_new') as opener,
        ):
            token = self._handler(interactive=True).get_access_token()
        assert token.access_token == 'CACHED'
        assert post.call_count == 0
        opener.assert_not_called()

    def test_parallel_local_callers_share_one_token_request(self) -> None:
        def slow_post(*_args, **_kwargs):
            time.sleep(0.1)
            return _token_response(_access_payload())

        post = mock.Mock(side_effect=slow_post)
        tokens = []
        errors = []

        def worker() -> None:
            try:
                tokens.append(self._handler(interactive=False).get_access_token().access_token)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        with (
            mock.patch('digikey.oauth.oauth2.requests.post', post),
            mock.patch('digikey.oauth.oauth2.open_new', side_effect=AssertionError('browser')),
        ):
            threads = [threading.Thread(target=worker) for _ in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
                assert not thread.is_alive()

        assert errors == []
        assert tokens == ['MOCK_ACCESS'] * 6
        assert post.call_count == 1

    def test_parallel_interactive_callers_open_one_browser(self) -> None:
        opened = []

        def fake_open(url) -> None:
            opened.append(url)
            time.sleep(0.05)

        post = mock.Mock(return_value=_token_response(_access_payload(refresh='MOCK_REFRESH')))
        ssl_context = mock.Mock()
        ssl_context.wrap_socket.side_effect = lambda sock, server_side=True: sock
        with (
            mock.patch('digikey.oauth.oauth2.open_new', side_effect=fake_open),
            mock.patch('digikey.oauth.oauth2.HTTPServer', FakeHTTPServer),
            mock.patch('digikey.oauth.oauth2.ssl.SSLContext', return_value=ssl_context),
            mock.patch.object(
                oauth2.TokenHandler,
                '_TokenHandler__generate_certificate',
                return_value='localhost.pem',
            ),
            mock.patch('digikey.oauth.oauth2.os.remove'),
            mock.patch('digikey.oauth.oauth2.requests.post', post),
        ):
            tokens = []
            errors = []

            def worker() -> None:
                try:
                    tokens.append(self._handler(interactive=True).get_access_token().access_token)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
                assert not thread.is_alive()

        assert errors == []
        assert tokens == ['MOCK_ACCESS'] * 4
        assert len(opened) == 1
        assert 'oauth2/authorize' in opened[0]
        assert post.call_count == 1
        assert post.call_args.kwargs['data']['grant_type'] == 'authorization_code'
        assert post.call_args.kwargs['data']['code'] == 'MOCK_AUTH_CODE'

    def test_explicit_interactive_overrides_local_tool_env(self) -> None:
        oauth2.use_local_tool()
        opened = []
        post = mock.Mock(return_value=_token_response(_access_payload(refresh='MOCK_REFRESH')))
        ssl_context = mock.Mock()
        ssl_context.wrap_socket.side_effect = lambda sock, server_side=True: sock
        with (
            mock.patch('digikey.oauth.oauth2.open_new', side_effect=opened.append),
            mock.patch('digikey.oauth.oauth2.HTTPServer', FakeHTTPServer),
            mock.patch('digikey.oauth.oauth2.ssl.SSLContext', return_value=ssl_context),
            mock.patch.object(
                oauth2.TokenHandler,
                '_TokenHandler__generate_certificate',
                return_value='localhost.pem',
            ),
            mock.patch('digikey.oauth.oauth2.os.remove'),
            mock.patch('digikey.oauth.oauth2.requests.post', post),
        ):
            token = self._handler(interactive=True).get_access_token()
        assert token.access_token == 'MOCK_ACCESS'
        assert len(opened) == 1
        assert post.call_args.kwargs['data']['grant_type'] == 'authorization_code'
