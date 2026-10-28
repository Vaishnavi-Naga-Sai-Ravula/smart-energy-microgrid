import io
import json
import unittest
from email.message import Message
from http.client import HTTPConnection
from types import SimpleNamespace
from unittest.mock import Mock

from backend.grid_engine import InputValidationError
from backend.server import GridSenseHandler
from tests import test_server


class ChunkedIntegrationTests(unittest.TestCase):
    setUp = test_server.ServerApiTests.setUp
    tearDown = test_server.ServerApiTests.tearDown
    request_json = test_server.ServerApiTests.request_json
    def test_chunked_official_sample_validation(self):
        status, sample = self.request_json('GET', '/api/sample')
        self.assertEqual(status, 200)
        body = json.dumps({'rows': sample['rows']}).encode()
        connection = HTTPConnection(self.host, self.port, timeout=5)
        connection.request('POST', '/api/validate', body=iter([body[:31], body[31:]]),
                           headers={'Content-Type': 'application/json'}, encode_chunked=True)
        response = connection.getresponse()
        result = json.loads(response.read())
        connection.close()
        self.assertEqual(response.status, 200, result)
        self.assertEqual(result['accepted_rows'], 24)


class RequestFramingTests(unittest.TestCase):
    def read(self, wire, headers):
        message = Message()
        for key, value in headers:
            message[key] = value
        handler = SimpleNamespace(headers=message, rfile=io.BytesIO(wire), connection=Mock())
        return GridSenseHandler._read_body(handler)

    def test_extensions_and_trailers(self):
        self.assertEqual(self.read(b'2;foo=bar\r\n{}\r\n0\r\nX-Check: yes\r\n\r\n',
                                  [('Transfer-Encoding', 'chunked')]), b'{}')

    def test_invalid_or_excessive_chunks(self):
        for wire in (b'ZZ\r\n', b'2\r\n{', b'2\r\n{}XX', b'200000\r\n',
                     b'0\r\ninvalid\r\n\r\n', b'1'*8193):
            with self.subTest(wire=wire[:20]), self.assertRaises(InputValidationError):
                self.read(wire, [('Transfer-Encoding', 'chunked')])

    def test_ambiguous_and_unsupported_headers(self):
        for headers in ([('Transfer-Encoding', 'chunked'), ('Content-Length', '2')],
                        [('Transfer-Encoding', 'gzip, chunked')],
                        [('Content-Length', '2'), ('Content-Length', '2')]):
            with self.subTest(headers=headers), self.assertRaises(InputValidationError):
                self.read(b'{}', headers)

    def test_fixed_length_and_truncation(self):
        self.assertEqual(self.read(b'{}', [('Content-Length', '2')]), b'{}')
        with self.assertRaises(InputValidationError):
            self.read(b'{', [('Content-Length', '2')])
