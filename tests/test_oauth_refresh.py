import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend import model_service as service


class OAuthRefreshTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            'ZOHO_CLIENT_ID': 'test-client', 'ZOHO_CLIENT_SECRET': 'private-secret',
            'ZOHO_REFRESH_TOKEN': 'private-refresh',
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.cache = patch.object(service, '_oauth_cache', None)
        self.cache.start()
        self.addCleanup(self.cache.stop)

    def response(self, payload):
        return SimpleNamespace(ok=True, status_code=200, json=lambda: payload)

    def test_reuses_token_then_refreshes_before_expiry(self):
        with patch.object(service.time, 'monotonic', return_value=100) as clock, patch.object(
            service.requests, 'post', return_value=self.response({'access_token': 'token-one', 'expires_in': 3600})
        ) as post:
            self.assertEqual(service._oauth_access_token(), 'token-one')
            clock.return_value = 200
            self.assertEqual(service._oauth_access_token(), 'token-one')
            self.assertEqual(post.call_count, 1)
            clock.return_value = 3641
            post.return_value = self.response({'access_token': 'token-two', 'expires_in': 3600})
            self.assertEqual(service._oauth_access_token(), 'token-two')
            self.assertEqual(post.call_count, 2)
            self.assertEqual(post.call_args.args[0], 'https://accounts.zoho.in/oauth/v2/token')
            self.assertFalse(post.call_args.kwargs['allow_redirects'])
            self.assertEqual(post.call_args.kwargs['data']['grant_type'], 'refresh_token')

    def test_refreshed_token_authenticates_batch_prediction(self):
        import pandas as pd
        frame = pd.read_csv("sample_test_input.csv").head(2)
        responses = [self.response({"access_token": "renewed", "expires_in": 3600}),
                     self.response({"status": "success", "result": [95.34, 93.14]})]
        with patch.object(service.requests, 'post', side_effect=responses) as post:
            values = service._quickml_predictions(frame, "https://example.invalid")
        self.assertEqual(values.tolist(), [95.34, 93.14])
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Zoho-oauthtoken renewed')
        self.assertEqual(len(post.call_args.kwargs['json']['data']), 2)

    def test_changed_credentials_invalidate_cache(self):
        with patch.object(service.requests, 'post', return_value=self.response({'access_token': 'a', 'expires_in': 3600})) as post:
            service._oauth_access_token()
            os.environ['ZOHO_REFRESH_TOKEN'] = 'replacement'
            service._oauth_access_token()
            self.assertEqual(post.call_count, 2)

    def test_static_token_compatibility(self):
        with patch.dict(os.environ, {'ZOHO_OAUTH_TOKEN': 'static'}, clear=True):
            self.assertEqual(service._oauth_access_token(), 'static')

    def test_partial_credentials_fail_before_network(self):
        del os.environ['ZOHO_CLIENT_SECRET']
        with patch.object(service.requests, 'post') as post:
            with self.assertRaises(service.ModelIntegrationError):
                service._oauth_access_token()
            post.assert_not_called()

    def test_untrusted_token_destination_rejected(self):
        os.environ['ZOHO_ACCOUNTS_URL'] = 'https://attacker.invalid'
        with patch.object(service.requests, 'post') as post:
            with self.assertRaises(service.ModelIntegrationError):
                service._oauth_access_token()
            post.assert_not_called()

    def test_malformed_or_rejected_tokens_are_redacted(self):
        for payload in ({'error': 'private-secret'}, {'access_token': 'a', 'expires_in': 'bad'},
                        {'access_token': 'a', 'expires_in': float('inf')}, [], {}):
            with self.subTest(payload=payload), patch.object(service.requests, 'post', return_value=self.response(payload)):
                with self.assertRaises(service.ModelIntegrationError) as caught:
                    service._oauth_access_token()
                self.assertNotIn('private-secret', str(caught.exception))

    def test_network_error_is_redacted(self):
        with patch.object(service.requests, 'post', side_effect=service.requests.ConnectionError('private-secret')):
            with self.assertRaises(service.ModelIntegrationError) as caught:
                service._oauth_access_token()
            self.assertNotIn('private-secret', str(caught.exception))

    def test_redirect_rejected(self):
        with patch.object(service.requests, 'post', return_value=SimpleNamespace(ok=True, status_code=302)):
            with self.assertRaises(service.ModelIntegrationError):
                service._oauth_access_token()
