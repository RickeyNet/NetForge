"""Minimal FDM (Firepower Device Manager) REST client, stdlib only.

Covers the post-console steps of FTD 1010 staging that would otherwise be
done by hand in the FDM web GUI:

  * token login                       POST fdm/token
  * accept EULA / skip device setup   GET+POST devices/default/action/provision
  * start the 90-day evaluation       POST license/smartagentconnections
  * deploy pending changes            POST operational/deploy (+ poll)
  * upload a firmware image           POST action/uploadupgrade (multipart)
  * start the upgrade                 POST action/upgrade

FDM uses a self-signed certificate out of the box, so certificate
verification is disabled - this client is for staging a directly attached
appliance, not for talking across an untrusted network.
"""

import json
import os
import ssl
import time
import uuid
import http.client
import urllib.error
import urllib.request

API_BASE = "/api/fdm/latest/"


class FdmError(Exception):
    pass


class FdmStopped(FdmError):
    """Raised when a long-running operation is cancelled via ``stop``."""


class FdmClient:
    def __init__(self, host, username="admin", password="", log=None,  # nosec B107 - empty default; the real password is supplied by the caller
                 timeout=30):
        self.host     = host.strip()
        self.username = username
        self.password = password
        self.log      = log or (lambda _msg: None)
        self.timeout  = timeout
        self._token        = None
        self._token_expiry = 0.0
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self._ctx = ctx

    # ------------------------------------------------------------ http
    def _url(self, path):
        return f"https://{self.host}{API_BASE}{path}"

    def _request(self, method, path, payload=None, auth=True, timeout=None):
        headers = {"Accept": "application/json"}
        if auth:
            self._ensure_token()
            headers["Authorization"] = f"Bearer {self._token}"
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self._url(path), data=body,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(  # nosec B310 - FDM REST client; URL is always built with a fixed https:// scheme
                    req, context=self._ctx,
                    timeout=timeout or self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise FdmError(
                f"{method} {path} -> HTTP {exc.code}: "
                f"{_error_detail(exc)}") from exc
        except urllib.error.URLError as exc:
            raise FdmError(f"{method} {path} -> {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            return {"raw": raw.decode("utf-8", errors="replace")}

    # ------------------------------------------------------------ auth
    def login(self):
        data = self._request("POST", "fdm/token", {
            "grant_type": "password",
            "username":   self.username,
            "password":   self.password,
        }, auth=False)
        token = data.get("access_token")
        if not token:
            raise FdmError(f"login succeeded but no access_token: {data}")
        self._token = token
        # Trust the server's lifetime when given; refresh early.
        try:
            lifetime = float(data.get("expires_in") or 30 * 60)
        except (TypeError, ValueError):
            lifetime = 30 * 60
        self._token_expiry = time.time() + max(60.0, lifetime - 5 * 60)
        self.log("FDM login OK\n")

    def _ensure_token(self):
        if not self._token or time.time() >= self._token_expiry:
            self.login()

    # ------------------------------------------- provisioning / license
    def accept_eula(self):
        """Complete initial provisioning (GUI: Skip Device Setup + EULA).

        Assumes the admin password was already changed on the console.
        Returns the provision object, or None if the device reports
        setup is already done.
        """
        data = self._request("GET", "devices/default/action/provision")
        items = data.get("items")
        prov = items[0] if items else data
        for key in ("links", "version"):
            prov.pop(key, None)
        prov["acceptEULA"] = True
        prov.setdefault("type", "initialprovision")
        try:
            result = self._request(
                "POST", "devices/default/action/provision", prov)
        except FdmError as exc:
            if "DeviceSetupAlreadyDone" in str(exc):
                self.log("Device setup already completed - nothing to do\n")
                return None
            raise
        self.log("EULA accepted / initial provisioning complete\n")
        return result

    def start_evaluation(self):
        """Start the 90-day evaluation license (no-op if already licensed)."""
        try:
            data = self._request("GET", "license/smartagentconnections")
            items = data.get("items") or []
        except FdmError:
            items = []
        for conn in items:
            ctype = (conn or {}).get("connectionType")
            if ctype in ("EVALUATION", "REGISTER"):
                self.log(f"License connection already {ctype} "
                         "- nothing to do\n")
                return conn
        result = self._request("POST", "license/smartagentconnections", {
            "type":           "smartagentconnection",
            "connectionType": "EVALUATION",
        })
        self.log("90-day evaluation started\n")
        return result

    # ---------------------------------------------------------- deploy
    def deploy(self, poll_interval=10, timeout=1800, progress=None,
               stop=None):
        """Deploy pending changes and poll until a terminal state.

        ``stop`` is an optional callable checked between polls; when it
        returns True the wait is abandoned with FdmStopped (the
        deployment itself continues on the device).
        """
        stop = stop or (lambda: False)
        job = self._request("POST", "operational/deploy")
        job_id = job.get("id")
        if not job_id:
            raise FdmError(f"deploy did not return a job id: {job}")
        deadline = time.time() + timeout
        state = job.get("state", "QUEUED")
        while state in ("QUEUED", "DEPLOYING") and time.time() < deadline:
            if progress:
                progress(state)
            self._sleep_unless_stopped(poll_interval, stop)
            job = self._request("GET", f"operational/deploy/{job_id}")
            state = job.get("state", state)
        if state != "DEPLOYED":
            raise FdmError(f"deployment ended in state {state}")
        self.log("Deployment complete\n")
        return job

    @staticmethod
    def _sleep_unless_stopped(seconds, stop):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if stop():
                raise FdmStopped("stopped by user")
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))

    # --------------------------------------------------------- upgrade
    def upload_upgrade(self, filepath, progress=None, stop=None,
                       chunk_size=1024 * 1024):
        """Stream a firmware image to the device (multipart upload).

        Streams from disk in chunks so a ~1 GB image never has to fit in
        memory. ``progress(sent_bytes, total_bytes)`` is called as the
        upload advances; ``stop`` is checked between chunks and aborts
        the upload with FdmStopped.
        """
        stop = stop or (lambda: False)
        self._ensure_token()
        boundary = "----netforge" + uuid.uuid4().hex
        fname = os.path.basename(filepath)
        preamble = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="fileToUpload"; '
            f'filename="{fname}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
        epilogue = f"\r\n--{boundary}--\r\n".encode("utf-8")
        size  = os.path.getsize(filepath)
        total = len(preamble) + size + len(epilogue)

        conn = http.client.HTTPSConnection(self.host, context=self._ctx,
                                           timeout=120)
        try:
            conn.putrequest("POST", API_BASE + "action/uploadupgrade")
            conn.putheader("Authorization", f"Bearer {self._token}")
            conn.putheader("Accept", "application/json")
            conn.putheader("Content-Type",
                           f"multipart/form-data; boundary={boundary}")
            conn.putheader("Content-Length", str(total))
            conn.endheaders()
            conn.send(preamble)
            sent = 0
            with open(filepath, "rb") as f:
                while True:
                    if stop():
                        raise FdmStopped("upload stopped by user")
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    conn.send(chunk)
                    sent += len(chunk)
                    if progress:
                        progress(sent, size)
            conn.send(epilogue)
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status >= 400:
                raise FdmError(
                    f"upload -> HTTP {resp.status}: "
                    f"{raw.decode('utf-8', errors='replace')[:300]}")
        finally:
            conn.close()
        self.log(f"Uploaded {fname} ({size:,} bytes)\n")
        return json.loads(raw) if raw else {}

    def start_upgrade(self):
        """Kick off the upgrade using the uploaded image.

        The device installs and reboots on its own afterwards (~45 min
        on an FTD 1010); the API goes away mid-upgrade, so this does not
        poll for completion.
        """
        result = self._request("POST", "action/upgrade", timeout=120)
        self.log("Upgrade started - device will install and reboot\n")
        return result


def _error_detail(exc):
    """Pull a readable message out of an FDM error response body."""
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return exc.reason
    try:
        data = json.loads(body)
        msgs = data.get("error", {}).get("messages", [])
        text = "; ".join(m.get("description", "") for m in msgs if m)
        return text or body[:300]
    except ValueError:
        return body[:300]
