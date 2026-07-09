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
from datetime import datetime, timedelta, timezone

API_BASE = "/api/fdm/latest/"


class FdmError(Exception):
    pass


class FdmStopped(FdmError):
    """Raised when a long-running operation is cancelled via ``stop``."""


class FdmUnavailable(FdmError):
    """Connection-level failure: the FDM API is unreachable or not ready.

    Distinct from FdmError so login can retry these (the API takes
    minutes to come up after first boot, and restarts after a keyring
    regeneration) while real HTTP errors - bad credentials, rejected
    payloads - still fail immediately.
    """


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
        self.log(f"[fdm] {method} {path}\n")
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
            raise FdmUnavailable(f"{method} {path} -> {exc.reason}") from exc
        except (TimeoutError, OSError, http.client.HTTPException) as exc:
            # A read timeout or a dropped/garbled connection surfaces as a
            # raw socket/http error, not a URLError - typical while the
            # FDM web server is still starting up.
            raise FdmUnavailable(f"{method} {path} -> {exc}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            return {"raw": raw.decode("utf-8", errors="replace")}

    # ------------------------------------------------------------ auth
    def login(self, wait=0.0, stop=None):
        """Fetch a bearer token, retrying while the API comes up.

        Connection-level failures (unreachable, timeout, dropped) are
        retried for up to ``wait`` seconds - the FDM API takes minutes
        to come up after the console setup, and restarts briefly after
        a keyring regeneration. HTTP errors such as bad credentials
        fail immediately. ``stop`` aborts the wait with FdmStopped.
        """
        stop = stop or (lambda: False)
        deadline = time.monotonic() + wait
        while True:
            try:
                data = self._attempt_login()
                break
            except FdmUnavailable as exc:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                self.log(f"FDM API not ready ({exc}) - retrying, "
                         f"will keep trying for {int(remaining)}s\n")
                self._sleep_unless_stopped(min(20.0, remaining), stop)
        token = data.get("access_token")
        if not token:
            raise FdmError(f"login succeeded but no access_token: {data}")
        self._store_token(data, token)

    def _attempt_login(self):
        return self._request("POST", "fdm/token", {
            "grant_type": "password",
            "username":   self.username,
            "password":   self.password,
        }, auth=False, timeout=60)

    def _store_token(self, data, token):
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
            # Kicks off initial provisioning on the device; the response
            # regularly takes well over the default timeout.
            result = self._request(
                "POST", "devices/default/action/provision", prov,
                timeout=300)
        except FdmError as exc:
            # Phrasing varies by build: older ones return the
            # DeviceSetupAlreadyDone key, newer ones a readable sentence.
            msg = str(exc)
            if ("DeviceSetupAlreadyDone" in msg
                    or "device setup is complete" in msg.lower()):
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
        }, timeout=120)
        self.log("90-day evaluation started\n")
        return result

    # ------------------------------------------------- web certificate
    def replace_web_cert(self, name="NetForge-Web-Cert",
                         common_name="netforge", days=1825):
        """Replace the management web server certificate with a fresh one.

        Recovery for the expired-cert upgrade failure (CSCwd11825) on
        out-of-box devices: generates a self-signed certificate locally,
        uploads it as an internal certificate object, and points the
        management web server at it - the API equivalent of System
        Settings > Management Access > Management Web Server in the GUI.
        The caller still has to deploy for it to take effect.
        """
        cert_pem, key_pem = _self_signed_pem(common_name, days)
        data = self._request("GET", "object/internalcertificates?limit=100")
        items = [it for it in (data.get("items") or []) if it]
        taken = {it.get("name") for it in items}
        base, n = name, 2
        while name in taken:
            name = f"{base}-{n}"
            n += 1
        payload = {
            "name": name,
            "cert": cert_pem,
            "privateKey": key_pem,
            "type": "internalcertificate",
        }
        # Builds whose cert objects carry a certType expect it on create.
        if any("certType" in it for it in items):
            payload["certType"] = "UPLOAD"
        cert_obj = self._request("POST", "object/internalcertificates",
                                 payload)
        self.log(f"Created internal certificate '{name}' "
                 f"(valid {days} days)\n")

        data = self._request("GET",
                             "devicesettings/default/webuicertificates")
        items = data.get("items")
        if not items:
            raise FdmError("no webuicertificate settings object found")
        settings = items[0]
        settings.pop("links", None)
        settings["certificate"] = {
            "id":   cert_obj.get("id"),
            "name": cert_obj.get("name", name),
            "type": cert_obj.get("type", "internalcertificate"),
        }
        result = self._request(
            "PUT",
            f"devicesettings/default/webuicertificates/{settings['id']}",
            settings)
        self.log("Management web server set to the new certificate - "
                 "deploy required to take effect\n")
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
        deadline = time.time() + timeout
        try:
            job = self._request("POST", "operational/deploy", timeout=120)
        except FdmUnavailable as exc:
            # Deploying a management web certificate change restarts the
            # web server, which drops this very request without a
            # response - but the deployment still starts on the device.
            self.log(f"Deploy request dropped ({exc}) - the web server "
                     "is likely restarting to apply the change; "
                     "reconnecting to find the deployment\n")
            job = self._recover_deploy_job(deadline, stop)
        job_id = job.get("id")
        if not job_id:
            raise FdmError(f"deploy did not return a job id: {job}")
        state = job.get("state", "QUEUED")
        while state in ("QUEUED", "DEPLOYING") and time.time() < deadline:
            if progress:
                progress(state)
            self._sleep_unless_stopped(poll_interval, stop)
            try:
                job = self._request("GET", f"operational/deploy/{job_id}")
            except FdmUnavailable:
                # Deploying a web certificate change restarts the web
                # server mid-deploy; keep polling until the deadline.
                continue
            except FdmError as exc:
                # The restart can also invalidate the token; get a fresh
                # one and keep polling instead of aborting.
                if "HTTP 401" not in str(exc):
                    raise
                self._token = None
                continue
            state = job.get("state", state)
        if state != "DEPLOYED":
            raise FdmError(f"deployment ended in state {state}")
        self.log("Deployment complete\n")
        return job

    def _recover_deploy_job(self, deadline, stop):
        """Reconnect after a dropped deploy POST and find the job.

        The old token may have died with the web server, so log in
        again (waiting for the API to come back), then look for a
        deployment already in flight. If none is found the request
        never reached the device, and posting again is safe.
        """
        self._token = None
        self.login(wait=max(30.0, deadline - time.time()), stop=stop)
        data = self._request("GET", "operational/deploy")
        active = [it for it in (data.get("items") or [])
                  if it and it.get("state") in ("QUEUED", "DEPLOYING")]
        if active:
            self.log("Found the in-progress deployment - "
                     "resuming polling\n")
            return active[-1]
        self.log("No deployment in progress after reconnecting - "
                 "requesting the deploy again\n")
        return self._request("POST", "operational/deploy", timeout=120)

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


def _self_signed_pem(common_name, days):
    """Generate a self-signed certificate; returns (cert_pem, key_pem).

    Country US + a common name, mirroring what the FDM GUI's
    "Create new Internal Certificate > Self-Signed" wizard asks for.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError as exc:
        raise FdmError(
            "The 'cryptography' package is required to generate a web "
            "certificate. Install it with:  pip install cryptography"
        ) from exc
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=days))
            .sign(key, hashes.SHA256()))
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()).decode()
    return cert_pem, key_pem


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
