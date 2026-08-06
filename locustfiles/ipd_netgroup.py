import json

from locust import HttpUser, task, between
from gevent.lock import Semaphore

from common.auth import Auth
from common.sites import SITES

# ==========================
# GLOBAL SHARED STATE
# ==========================
# Module-level (not class-level) so it is really shared across every
# simulated user of this process, instead of being re-initialized per
# HttpUser instance - see locustfiles/config_admindata.py for the same
# pattern and rationale.
TOPOLOGY_LOCK = Semaphore()
TOPOLOGY_INITIALIZED = False


def _ip_from_netid(netid, host):
    oct1, oct2, oct3, _ = netid.split(".")
    return f"{oct1}.{oct2}.{oct3}.{host}"


def _mac_for(site_idx, subnet_idx, host):
    # Locally-administered, clearly-fake MAC range (02:xx...), derived
    # only from the topology's own coordinates so it stays stable across
    # runs instead of being random.
    return f"02:00:{site_idx:02x}:{subnet_idx:02x}:{host:02x}:00"


def build_topology():
    """
    Static IPDiscover topology : one netgroup per site (agency/city),
    each with a fixed set of networks (office LAN, server room LAN),
    each with a fixed set of network equipment (switch, printers,
    servers).

    Everything here is deterministic (same nettags/IPs/names on every
    run) so it can be safely checked for existence and reused instead of
    re-created on every locust launch.
    """
    topology = []

    for site_idx, site in enumerate(SITES):
        second_octet = 10 + site_idx

        topology.append(
            {
                "netgroup_name": site["city"],
                "netgroup_description": f"Agence de {site['city']}",
                "networks": [
                    {
                        "nettag": f"{site['code']}-LAN",
                        "name": f"{site['city']} - LAN bureautique",
                        "description": "Reseau bureautique (postes, imprimantes)",
                        "netid": f"10.{second_octet}.1.0",
                        "mask": "255.255.255.0",
                        "devices": [
                            {"suffix": "SWITCH-01", "host": 254},
                            {"suffix": "PRINTER-01", "host": 10},
                            {"suffix": "PRINTER-02", "host": 11},
                        ],
                    },
                    {
                        "nettag": f"{site['code']}-SRV",
                        "name": f"{site['city']} - LAN serveurs",
                        "description": "Reseau salle serveurs",
                        "netid": f"10.{second_octet}.2.0",
                        "mask": "255.255.255.0",
                        "devices": [
                            {"suffix": "SWITCH-01", "host": 254},
                            {"suffix": "SERVER-01", "host": 10},
                            {"suffix": "SERVER-02", "host": 11},
                        ],
                    },
                ],
            }
        )

    return topology


class NetgroupAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None

    def on_start(self):
        """
        Retrieve auth token at startup
        """
        self.token = Auth.get_token(self)

    # ==========================
    # HELPERS
    # ==========================
    def _headers(self):
        return {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
        }

    def find_existing_netgroup(self, name):
        response = self.client.get(
            "/netgroups/",
            headers=self._headers(),
            params={"name": name},
            name="/netgroups/?name=[name]",
        )

        if response.status_code != 200:
            return None

        try:
            results = response.json()
        except Exception:
            return None

        if isinstance(results, dict):
            results = results.get("results", [])

        return results[0] if results else None

    def ensure_netgroup(self, name, description):
        existing = self.find_existing_netgroup(name)
        if existing:
            return existing.get("id")

        response = self.client.post(
            "/netgroups/",
            headers=self._headers(),
            data=json.dumps({"name": name, "description": description}),
        )

        if response.status_code not in (200, 201):
            print("An error occured when attempt to POST netgroup : ", response.text)
            return None

        try:
            return response.json().get("id")
        except Exception:
            return None

    def find_existing_network(self, nettag):
        response = self.client.get(
            "/networks/",
            headers=self._headers(),
            params={"nettag": nettag},
            name="/networks/?nettag=[nettag]",
        )

        if response.status_code != 200:
            return None

        try:
            results = response.json()
        except Exception:
            return None

        if isinstance(results, dict):
            results = results.get("results", [])

        return results[0] if results else None

    def ensure_network(self, net_def, netgroup_id):
        existing = self.find_existing_network(net_def["nettag"])
        if existing:
            return existing.get("id")

        payload = {
            "nettag": net_def["nettag"],
            "name": net_def["name"],
            "description": net_def["description"],
            "netid": net_def["netid"],
            "mask": net_def["mask"],
            "group": netgroup_id,
            # Backend quirk (confirmed live against back.ocstest.fr):
            # NetworkSerializer declares "netdevices" as required, but its
            # create() calls `self.fields["netdevices"].create(...)` on
            # what DRF actually builds for it (a plain ManyRelatedField),
            # which has no such method - so this call ALWAYS reports an
            # error, empty list or not. The Network row (with the "group"
            # above already applied) is inserted right before that crash
            # though, so the request still does its job - see the 400
            # fallback below, which just goes and fetches what was
            # actually persisted. The real IPDiscover scan task sidesteps
            # this entirely by writing straight to the ORM (see
            # automation/tasks/ipdiscoverScan.py::insert_subnet) instead
            # of going through this REST endpoint; locust has no such
            # shortcut, hence this workaround.
            "netdevices": [],
        }
        response = self.client.post(
            "/networks/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if response.status_code in (200, 201):
            try:
                return response.json().get("id")
            except Exception:
                return None

        # Expected 400 (see comment above) - recover the id of the row
        # that was actually created instead of giving up on this network.
        created = self.find_existing_network(net_def["nettag"])
        if created:
            return created.get("id")

        print("An error occured when attempt to POST network : ", response.text)
        return None

    def find_existing_netdevice(self, network_id, ip):
        response = self.client.get(
            "/netdevices/",
            headers=self._headers(),
            params={"network": network_id, "ip": ip},
            name="/netdevices/?network=[id]&ip=[ip]",
        )

        if response.status_code != 200:
            return None

        try:
            results = response.json()
        except Exception:
            return None

        if isinstance(results, dict):
            results = results.get("results", [])

        return results[0] if results else None

    def ensure_netdevice(self, network_id, ip, netname, mac):
        if self.find_existing_netdevice(network_id, ip):
            return

        payload = {
            "ip": ip,
            "netname": netname,
            "mac": mac,
            "network": network_id,
        }
        response = self.client.post(
            "/netdevices/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if response.status_code not in (200, 201):
            print("An error occured when attempt to POST netdevice : ", response.text)

    # ==========================
    # TASK
    # ==========================
    @task
    def seed_ipdiscover_topology(self):
        """
        Ensure the fixed IPDiscover topology (netgroups > networks >
        netdevices) exists, checking for it on every launch instead of
        creating it blindly - this is the single source of truth for
        network groups/networks/equipment, so other locustfiles can rely
        on them existing.
        """
        if not self.token:
            print("Token not available, request not executed")
            return

        global TOPOLOGY_INITIALIZED

        with TOPOLOGY_LOCK:
            if TOPOLOGY_INITIALIZED:
                return

            for site_idx, site_entry in enumerate(build_topology()):
                netgroup_id = self.ensure_netgroup(
                    site_entry["netgroup_name"], site_entry["netgroup_description"]
                )
                if not netgroup_id:
                    continue

                for subnet_idx, net_def in enumerate(site_entry["networks"], start=1):
                    network_id = self.ensure_network(net_def, netgroup_id)
                    if not network_id:
                        continue

                    for device in net_def["devices"]:
                        ip = _ip_from_netid(net_def["netid"], device["host"])
                        netname = f"{net_def['nettag']}-{device['suffix']}"
                        mac = _mac_for(site_idx, subnet_idx, device["host"])
                        self.ensure_netdevice(network_id, ip, netname, mac)

            TOPOLOGY_INITIALIZED = True
