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
    FdmUnavailable,
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

    def test_timeout_becomes_fdmunavailable(self):
        # A raw socket read timeout is not a URLError; it must still
        # surface as an FdmError (naming the call) rather than escape.
        self.server.add("POST", "fdm/token",
                        TimeoutError("The read operation timed out"))
        with self.assertRaises(FdmUnavailable) as ctx:
            self.client.login()
        self.assertIn("fdm/token", str(ctx.exception))

    def test_login_retries_while_api_comes_up(self):
        self.server.add("POST", "fdm/token", [
            TimeoutError("The read operation timed out"),
            {"access_token": "TOK", "expires_in": 1800},
        ])
        self.client.login(wait=0.2)
        self.assertEqual(self.client._token, "TOK")
        self.assertEqual(len(self.server.payloads("POST", "fdm/token")), 2)

    def test_login_does_not_retry_bad_credentials(self):
        # HTTP errors (wrong password) must fail immediately even with a
        # wait budget - only connection-level failures are retried.
        self.server.add("POST", "fdm/token",
                        http_error(400, {"error": {"messages": [
                            {"description": "bad credentials"}]}}))
        with self.assertRaises(FdmError):
            self.client.login(wait=60)
        self.assertEqual(len(self.server.payloads("POST", "fdm/token")), 1)

    def test_stop_aborts_login_wait(self):
        self.server.add("POST", "fdm/token",
                        TimeoutError("The read operation timed out"))
        with self.assertRaises(FdmStopped):
            self.client.login(wait=60, stop=lambda: True)

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

    def test_already_done_prose_message_returns_none(self):
        # Some builds phrase the 422 as a sentence instead of the
        # DeviceSetupAlreadyDone key (seen live on FTD 7.0.1).
        self._with_token()
        self.server.add("GET", "devices/default/action/provision",
                        {"items": [{"type": "initialprovision"}]})
        self.server.add("POST", "devices/default/action/provision",
                        http_error(422, {"error": {"messages": [
                            {"description":
                             "The initial device setup is complete. You "
                             "can now manage the device and change the "
                             "configuration."}]}}))
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


class TestReplaceWebCert(_ApiTest):
    def _routes(self, existing_names=("DefaultInternalCertificate",)):
        self._with_token()
        self.server.add("GET", "object/internalcertificates?limit=100",
                        {"items": [{"name": n, "certType": "SELF_SIGNED",
                                    "id": f"c-{i}"}
                                   for i, n in enumerate(existing_names)]})
        self.server.add("POST", "object/internalcertificates",
                        {"id": "c-new", "name": "whatever",
                         "type": "internalcertificate"})
        self.server.add("GET", "devicesettings/default/webuicertificates",
                        {"items": [{"id": "w1", "type": "webuicertificate",
                                    "certificate": {"id": "c-0"},
                                    "links": {"self": "x"}}]})
        self.server.add("PUT",
                        "devicesettings/default/webuicertificates/w1",
                        {"ok": 1})

    def test_creates_cert_and_assigns_it(self):
        self._routes()
        self.client.replace_web_cert()
        posted = self.server.payloads(
            "POST", "object/internalcertificates")[0]
        self.assertIn("BEGIN CERTIFICATE", posted["cert"])
        self.assertIn("PRIVATE KEY", posted["privateKey"])
        self.assertEqual(posted["type"], "internalcertificate")
        # Existing objects carry certType, so the upload declares one.
        self.assertEqual(posted["certType"], "UPLOAD")
        put = self.server.payloads(
            "PUT", "devicesettings/default/webuicertificates/w1")[0]
        self.assertEqual(put["certificate"]["id"], "c-new")
        self.assertNotIn("links", put)

    def test_name_collision_gets_a_suffix(self):
        self._routes(existing_names=("DefaultInternalCertificate",
                                     "NetForge-Web-Cert"))
        self.client.replace_web_cert()
        posted = self.server.payloads(
            "POST", "object/internalcertificates")[0]
        self.assertEqual(posted["name"], "NetForge-Web-Cert-2")

    def test_certtype_omitted_when_unknown_to_build(self):
        self._with_token()
        self.server.add("GET", "object/internalcertificates?limit=100",
                        {"items": [{"name": "DefaultInternalCertificate",
                                    "id": "c-0"}]})
        self.server.add("POST", "object/internalcertificates",
                        {"id": "c-new", "type": "internalcertificate"})
        self.server.add("GET", "devicesettings/default/webuicertificates",
                        {"items": [{"id": "w1", "type": "webuicertificate",
                                    "certificate": {"id": "c-0"}}]})
        self.server.add("PUT",
                        "devicesettings/default/webuicertificates/w1",
                        {"ok": 1})
        self.client.replace_web_cert()
        posted = self.server.payloads(
            "POST", "object/internalcertificates")[0]
        self.assertNotIn("certType", posted)


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

    def test_poll_rides_out_web_server_restart(self):
        # Deploying a web-cert change restarts the FDM web server; a
        # dropped poll must not abort the wait.
        self._with_token()
        self.server.add("POST", "operational/deploy",
                        {"id": "j", "state": "QUEUED"})
        self.server.add("GET", "operational/deploy/j",
                        [TimeoutError("The read operation timed out"),
                         {"state": "DEPLOYED"}])
        job = self.client.deploy(poll_interval=0)
        self.assertEqual(job["state"], "DEPLOYED")

    def test_dropped_deploy_post_finds_running_job(self):
        # Deploying a web-cert change restarts the web server, which
        # closes the deploy POST itself without a response ("Remote end
        # closed connection without response") - but the deployment
        # still starts. The client must reconnect and pick it up.
        self._with_token()
        self.server.add("POST", "operational/deploy",
                        TimeoutError("Remote end closed connection "
                                     "without response"))
        self.server.add("GET", "operational/deploy",
                        {"items": [{"id": "done", "state": "DEPLOYED"},
                                   {"id": "j9", "state": "DEPLOYING"}]})
        self.server.add("GET", "operational/deploy/j9",
                        [{"state": "DEPLOYED"}])
        job = self.client.deploy(poll_interval=0)
        self.assertEqual(job["state"], "DEPLOYED")
        # A fresh token was fetched after the restart.
        self.assertEqual(len(self.server.payloads("POST", "fdm/token")), 2)

    def test_dropped_deploy_post_reposts_when_no_job_found(self):
        # If the dropped request never reached the device there is no
        # job to resume - deploying again is the safe recovery.
        self._with_token()
        self.server.add("POST", "operational/deploy",
                        [TimeoutError("Remote end closed connection "
                                      "without response"),
                         {"id": "j2", "state": "QUEUED"}])
        self.server.add("GET", "operational/deploy", {"items": []})
        self.server.add("GET", "operational/deploy/j2",
                        [{"state": "DEPLOYED"}])
        job = self.client.deploy(poll_interval=0)
        self.assertEqual(job["state"], "DEPLOYED")
        self.assertEqual(
            len(self.server.payloads("POST", "operational/deploy")), 2)

    def test_poll_relogins_when_restart_invalidates_token(self):
        self._with_token()
        self.server.add("POST", "operational/deploy",
                        {"id": "j", "state": "QUEUED"})
        self.server.add("GET", "operational/deploy/j",
                        [http_error(401, {"error": {"messages": [
                            {"description": "Invalid token"}]}}),
                         {"state": "DEPLOYED"}])
        job = self.client.deploy(poll_interval=0)
        self.assertEqual(job["state"], "DEPLOYED")
        self.assertEqual(len(self.server.payloads("POST", "fdm/token")), 2)

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

    def test_announces_upload_before_streaming(self):
        # The upload takes many minutes with no other API traffic; the
        # transcript must say it started, not just that it finished.
        msgs = []
        self.client.log = msgs.append
        self.client.upload_upgrade(self.path, chunk_size=4)
        self.assertIn("uploading", msgs[0])
        self.assertIn("20 bytes", msgs[0])

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
