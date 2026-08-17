import json

from locust import HttpUser, task, between
from gevent.lock import Semaphore

from common.auth import Auth
from common.sites import SITES, subnet_cidrs

# ==========================
# GLOBAL SHARED STATE
# ==========================
# Module-level (not class-level) so it is really shared across every
# simulated user of this process - see locustfiles/ipd_netgroup.py for
# the same pattern and rationale.
SNMP_LOCK = Semaphore()
SNMP_INITIALIZED = False

SNMP_VERSION = "2c"
# How many real, already-inventoried assets each fake scanner claims to
# have matched - a real SnmpScanner.assets is populated from actual scan
# hits, so this links to genuine InventoryBase rows instead of inventing
# ids, same spirit as ipd_netgroup.py seeding real netdevices.
ASSETS_PER_SCANNER = 6


def _probe_ip(lan_cidr):
    """
    A plausible, fixed probe/host address for the scanner itself inside
    a site's office-LAN subnet - .250, distinct from the switch/printer
    hosts (.10/.11/.254) ipd_netgroup.py's build_topology() already uses
    on that same subnet.
    """
    network = lan_cidr.split("/")[0]
    prefix = network.rsplit(".", 1)[0]
    return f"{prefix}.250"


class SnmpAPITest(HttpUser):
    """
    Seeds one SnmpConfig + one SnmpScanner per site (common/sites.py),
    reusing the exact subnets ipd_netgroup.py's IPDiscover topology
    already seeded there - so the SNMP section of the demo isn't an
    unrelated, disconnected data set, but the same site network "scanned"
    through a second discovery method.
    """

    wait_time = between(1, 5)
    token = None

    def on_start(self):
        self.token = Auth.get_token(self)

    # ==========================
    # HELPERS
    # ==========================
    def _headers(self):
        return {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
        }

    def find_existing_config(self, name):
        response = self.client.get(
            "/snmp/config/",
            headers=self._headers(),
            params={"name": name},
            name="/snmp/config/?name=[name]",
        )

        if response.status_code != 200:
            return None

        try:
            results = response.json()
        except Exception:
            return None

        if isinstance(results, dict):
            results = results.get("results", [])

        return next((c for c in results if c.get("name") == name), None)

    def ensure_config(self, site, subnets):
        name = f"{site['city']} - SNMP v2c"
        existing = self.find_existing_config(name)
        if existing:
            return existing.get("id")

        payload = {
            "name": name,
            "version": SNMP_VERSION,
            "user": "public",
            "subnets": subnets,
            "retries": 3,
            "timeout": 3,
        }
        response = self.client.post(
            "/snmp/config/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if response.status_code not in (200, 201):
            print("An error occured when attempt to POST snmp config : ", response.text)
            return None

        try:
            return response.json().get("id")
        except Exception:
            return None

    def find_existing_scanner(self, name):
        response = self.client.get(
            "/snmp/scanner/",
            headers=self._headers(),
            params={"name": name},
            name="/snmp/scanner/?name=[name]",
        )

        if response.status_code != 200:
            return None

        try:
            results = response.json()
        except Exception:
            return None

        if isinstance(results, dict):
            results = results.get("results", [])

        return next((s for s in results if s.get("name") == name), None)

    def fetch_sample_asset_ids(self, size):
        response = self.client.get(
            "/asset/bases/",
            headers=self._headers(),
            params={"limit": size},
            name="/asset/bases/?limit=[size]",
        )

        if response.status_code != 200:
            return []

        try:
            results = response.json()
        except Exception:
            return []

        if isinstance(results, dict):
            results = results.get("results", [])

        return [a["id"] for a in results if a.get("id")]

    def ensure_scanner(self, site, subnets, config_id):
        name = f"Scanner SNMP - {site['city']}"
        if self.find_existing_scanner(name):
            return

        payload = {
            "name": name,
            "ip": _probe_ip(subnets[0]),
            "subnets": subnets,
            "notes": f"Sonde de decouverte SNMP pour l'agence de {site['city']}.",
            "configs": [config_id] if config_id else [],
            "assets": self.fetch_sample_asset_ids(ASSETS_PER_SCANNER),
        }
        response = self.client.post(
            "/snmp/scanner/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if response.status_code not in (200, 201):
            print("An error occured when attempt to POST snmp scanner : ", response.text)

    # ==========================
    # TASK
    # ==========================
    @task
    def seed_snmp_topology(self):
        """
        Ensure one SnmpConfig + one SnmpScanner per site exists, checking
        for it on every launch instead of creating it blindly.
        """
        if not self.token:
            print("Token not available, request not executed")
            return

        global SNMP_INITIALIZED

        with SNMP_LOCK:
            if SNMP_INITIALIZED:
                return

            for site_idx, site in enumerate(SITES):
                subnets = subnet_cidrs(site_idx)
                config_id = self.ensure_config(site, subnets)
                self.ensure_scanner(site, subnets, config_id)

            SNMP_INITIALIZED = True
