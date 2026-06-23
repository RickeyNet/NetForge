"""Tests for the FDM REST client (netforge/ftd/fdm_api.py).

The client is pure stdlib, so the network is faked: urllib.request.urlopen
is replaced with a scripted router for the JSON endpoints, and
http.client.HTTPSConnection is replaced for the multipart firmware upload.
"""

import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

import netforge.ftd.fdm_api as fdm_api
from netforge.ftd.fdm_api import (
    API_BASE,
    FdmClient,
    FdmError,
    FdmStopped,
    _error_detail,
)


def http_error(code, body):
    """Build an HTTPError whose body the client can read for its detail."""
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return urllib.error.HTTPError(
        "https://host" + API_BASE + "p", code, "msg", {}, io.BytesIO(raw))


class _Resp:
    def __init__(self, body):
        self._body = (body if isinstance(body, bytes)
                      else json.dumps(body).encode())

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class FakeServer:
    """Routes (method, path) -> response. A list is consumed in sequence."""

    def __init__(self):
        self.routes = {}
        self.requests = []   # (method, path, payload-or-None)

    def add(self, method, path, response):
        self.routes[(method, path)] = response

    def urlopen(self, req, context=None, timeout=None):
        method = req.get_method()
        path = req.full_url.split(API_BASE, 1)[-1]
        payload = json.loads(req.data.decode()) if req.data else None
        self.requests.append((method, path, payload))
        if (method, path) not in self.routes:
            raise AssertionError(f"unexpected request: {method} {path}")
        resp = self.routes[(method, path)]
        if isinstance(resp, list):
            resp = resp.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return _Resp(resp)

    def payloads(self, method, path):
        return [p for (m, pa, p) in self.requests if m == method and pa == path]


class _ApiTest(unittest.TestCase):
    def setUp(self):
        self.server = FakeServer()
        self.patcher = mock.patch.object(
            fdm_api.urllib.request, "urlopen", self.server.urlopen)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = FdmClient("10.0.0.1", username="admin", password="pw")

    def _with_token(self):
        self.server.add("POST", "fdm/token",
                        {"access_token": "TOK", "expires_in": 1800})


class TestLogin(_ApiTest):
    def test_login_sets_token(self):
        self._with_token()
        self.client.login()
        self.assertEqual(self.client._token, "TOK")
        self.assertEqual(self.server.payloads("POST", "fdm/token")[0],
                         {"grant_type": "password",
                          "username": "admin", "password": "pw"})

    def test_login_without_access_token_raises(self):
        self.server.add("POST", "fdm/token", {"message": "nope"})
        with self.assertRaises(FdmError):
            self.client.login()

    def test_request_auto_logs_in_once(self):
        self._with_token()
        self.server.add("GET", "license/smartagentconnections",
                        {"items": [{"connectionType": "EVALUATION"}]})
        self.client.start_evaluation()
        # The token endpoint should be hit exactly once and reused.
        self.assertEqual(len(self.server.payloads("POST", "fdm/token")), 1)


class TestRequestErrors(_ApiTest):
    def test_http_error_becomes_fdmerror_with_detail(self):
        self._with_token()
        self.server.add("GET", "license/smartagentconnections",
                        http_error(422, {"error": {"messages": [
                            {"description": "license boom"}]}}))
        # start_evaluation swallows the GET error, so call _request directly.
        self.client.login()
        with self.assertRaises(FdmError) as ctx:
            self.client._request("GET", "license/smartagentconnections")
        self.assertIn("license boom", str(ctx.exception))

    def test_error_detail_parses_messages(self):
        exc = http_error(400, {"error": {"messages": [
            {"description": "first"}, {"description": "second"}]}})
        self.assertEqual(_error_detail(exc), "first; second")

    def test_error_detail_falls_back_to_body(self):
        exc = http_error(500, b"plain text failure")
        self.assertEqual(_error_detail(exc), "plain text failure")


class TestAcceptEula(_ApiTest):
    def test_accepts_and_posts_eula_flag(self):
        self._with_token()
        self.server.add("GET", "devices/default/action/provision",
                        {"items": [{"type": "initialprovision",
                                    "links": {"self": "x"}, "version": "1"}]})
        self.server.add("POST", "devices/default/action/provision",
                        {"ok": True})
        result = self.client.accept_eula()
        self.assertEqual(result, {"ok": True})
        sent = self.server.payloads(
            "POST", "devices/default/action/provision")[0]
        self.assertTrue(sent["acceptEULA"])
        # links/version are stripped before re-posting.
        self.assertNotIn("links", sent)
        self.assertNotIn("version", sent)

    def test_already_done_returns_none(self):
        self._with_token()
        self.server.add("GET", "devices/default/action/provision",
                        {"items": [{"type": "initialprovision"}]})
        self.server.add("POST", "devices/default/action/provision",
                        http_error(422, {"error": {"messages": [
                            {"description": "DeviceSetupAlreadyDone"}]}}))
        self.assertIsNone(self.client.accept_eula())


class TestStartEvaluation(_ApiTest):
    def test_starts_when_unlicensed(self):
        self._with_token()
        self.server.add("GET", "license/smartagentconnections", {"items": []})
        self.server.add("POST", "license/smartagentconnections", {"ok": 1})
        self.client.start_evaluation()
        posted = self.server.payloads("POST", "license/smartagentconnections")
        self.assertEqual(posted[0]["connectionType"], "EVALUATION")

    def test_skips_when_already_licensed(self):
        self._with_token()
        self.server.add("GET", "license/smartagentconnections",
                        {"items": [{"connectionType": "REGISTER"}]})
        self.client.start_evaluation()
        self.assertEqual(
            self.server.payloads("POST", "license/smartagentconnections"), [])


class TestDeploy(_ApiTest):
    def test_polls_until_deployed(self):
        self._with_token()
        self.server.add("POST", "operational/deploy",
                        {"id": "job1", "state": "QUEUED"})
        self.server.add("GET", "operational/deploy/job1",
                        [{"state": "DEPLOYING"}, {"state": "DEPLOYED"}])
        states = []
        job = self.client.deploy(poll_interval=0,
                                 progress=states.append)
        self.assertEqual(job["state"], "DEPLOYED")
        self.assertIn("QUEUED", states)

    def test_no_job_id_raises(self):
        self._with_token()
        self.server.add("POST", "operational/deploy", {})
        with self.assertRaises(FdmError):
            self.client.deploy(poll_interval=0)

    def test_bad_end_state_raises(self):
        self._with_token()
        self.server.add("POST", "operational/deploy",
                        {"id": "j", "state": "QUEUED"})
        self.server.add("GET", "operational/deploy/j", [{"state": "FAILED"}])
        with self.assertRaises(FdmError):
            self.client.deploy(poll_interval=0)

    def test_stop_raises_fdmstopped(self):
        self._with_token()
        self.server.add("POST", "operational/deploy",
                        {"id": "j", "state": "QUEUED"})
        with self.assertRaises(FdmStopped):
            self.client.deploy(poll_interval=0.05, stop=lambda: True)


class _FakeUploadResp:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body


class _FakeConn:
    status = 200
    body = b'{"id": "upload1"}'
    instances = []

    def __init__(self, host, context=None, timeout=None):
        self.host = host
        self.sent = bytearray()
        _FakeConn.instances.append(self)

    def putrequest(self, *a, **k):
        pass

    def putheader(self, *a, **k):
        pass

    def endheaders(self):
        pass

    def send(self, data):
        self.sent.extend(data)

    def getresponse(self):
        return _FakeUploadResp(_FakeConn.status, _FakeConn.body)

    def close(self):
        pass


class TestUpload(unittest.TestCase):
    def setUp(self):
        _FakeConn.instances = []
        _FakeConn.status = 200
        _FakeConn.body = b'{"id": "upload1"}'
        self.client = FdmClient("10.0.0.1", password="pw")
        # Skip auth: pretend we already hold a valid token.
        self.client._token = "TOK"
        self.client._token_expiry = 10 ** 18
        self.conn_patch = mock.patch.object(
            fdm_api.http.client, "HTTPSConnection", _FakeConn)
        self.conn_patch.start()
        self.addCleanup(self.conn_patch.stop)
        fd, self.path = tempfile.mkstemp()
        os.write(fd, b"FIRMWARE-IMAGE-BYTES")
        os.close(fd)
        self.addCleanup(os.remove, self.path)

    def test_streams_file_and_reports_progress(self):
        seen = []
        result = self.client.upload_upgrade(
            self.path, progress=lambda s, t: seen.append((s, t)),
            chunk_size=4)
        self.assertEqual(result, {"id": "upload1"})
        sent = bytes(_FakeConn.instances[0].sent)
        self.assertIn(b"FIRMWARE-IMAGE-BYTES", sent)
        self.assertIn(b"netforge", sent)            # multipart boundary
        self.assertEqual(seen[-1], (20, 20))        # full file accounted for

    def test_stop_aborts_upload(self):
        with self.assertRaises(FdmStopped):
            self.client.upload_upgrade(self.path, stop=lambda: True,
                                       chunk_size=4)

    def test_http_error_status_raises(self):
        _FakeConn.status = 500
        _FakeConn.body = b"boom"
        with self.assertRaises(FdmError):
            self.client.upload_upgrade(self.path, chunk_size=4)


class TestStartUpgrade(_ApiTest):
    def test_posts_upgrade(self):
        self._with_token()
        self.server.add("POST", "action/upgrade", {"state": "started"})
        result = self.client.start_upgrade()
        self.assertEqual(result, {"state": "started"})
        self.assertEqual(len(self.server.payloads("POST", "action/upgrade")), 1)


if __name__ == "__main__":
    unittest.main()
