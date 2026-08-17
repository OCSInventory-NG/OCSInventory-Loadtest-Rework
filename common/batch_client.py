"""
Small requests-based client for end-of-run, fleet-wide batch jobs.

Locustfiles sometimes need a piece of work to happen exactly once, over
every object on the platform, when the test stops (see
`locust.events.test_stop` listeners in config_admindata.py /
asset_log_history.py) - not scattered across whatever a random subset of
simulated users happened to touch during the run. That work runs outside
of any Locust User/HttpSession, so it needs its own tiny HTTP client.
"""

import requests


class HostPrefixedSession:
    """
    Thin shim exposing the get/post/patch(path, ...) signature that
    `common.auth.Auth` and batch-job helpers expect, backed by a plain
    `requests.Session` (Locust's HttpSession auto-prefixes the host, a
    plain session doesn't).
    """

    def __init__(self, host):
        self.session = requests.Session()
        self.host = host.rstrip("/")

    def _url(self, path):
        return f"{self.host}{path}"

    def get(self, path, **kwargs):
        return self.session.get(self._url(path), **kwargs)

    def post(self, path, **kwargs):
        return self.session.post(self._url(path), **kwargs)

    def patch(self, path, **kwargs):
        return self.session.patch(self._url(path), **kwargs)


class BatchUser:
    """Minimal stand-in so `common.auth.Auth.get_token(self)` can be reused as-is."""

    def __init__(self, host):
        self.client = HostPrefixedSession(host)
