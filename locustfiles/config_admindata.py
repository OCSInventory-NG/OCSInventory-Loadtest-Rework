import json
import random

from locust import HttpUser, events, task, between
from locust.runners import WorkerRunner
from gevent.lock import Semaphore

from common.auth import Auth
from common.batch_client import BatchUser
from common.sites import SITES

# ==========================
# GLOBAL SHARED STATE
# ==========================
# Module-level (not class-level) so it is really shared across every
# simulated user of this process, instead of being re-initialized per
# HttpUser instance.
ADMINDATA_LOCK = Semaphore()
ADMINDATA_INITIALIZED = False

ASSET_OBJECT_SLUG = "inventory_base.inventorybase"
IPDISCOVER_OBJECT_SLUG = "netdevice.netdevice"

# TAG (free text) and Location (SELECT) both derive from the same site,
# so an asset tagged "PAR-..." is consistently located in "Paris" - see
# _build_random_accountdata, which picks one site per asset and reuses it
# for both fields instead of rolling them independently.
TAG_TYPE_CODES = {
    "Desktop": "DT",
    "Laptop": "LT",
    "Server": "SRV",
    "Virtual Machine": "VM",
    "Tablet": "TAB",
    "Smartphone": "SP",
}


class AdmindataAPITest(HttpUser):
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

    def find_existing_config(self, name, datatarget):
        """
        Look up an existing accountinfo config by (name, datatarget) -
        the pair the backend enforces as unique - and expand it with its
        current values so callers can diff against them.

        Returns the config dict, or None if it doesn't exist yet.
        """
        response = self.client.get(
            "/accountinfo/config/",
            headers=self._headers(),
            params={"name": name, "datatarget": datatarget, "expand": "accountinfo_values"},
            name="/accountinfo/config/?name=[name]&datatarget=[datatarget]",
        )

        if response.status_code != 200:
            return None

        try:
            results = response.json()
        except Exception:
            return None

        # LimitOffsetPagination returns a plain list when no ?limit= is
        # passed, but stay defensive in case that ever changes.
        if isinstance(results, dict):
            results = results.get("results", [])

        return results[0] if results else None

    def create_config(self, cfg):
        """
        Create a config and return its id, or None on error.
        """
        response = self.client.post(
            "/accountinfo/config/",
            headers=self._headers(),
            data=json.dumps(cfg),
        )

        if response.status_code not in (200, 201):
            try:
                error_msg = response.json().get("error", response.text)
            except Exception:
                error_msg = response.text
            print(
                "An error occured when attempt to POST admindata config : ",
                error_msg,
            )
            return None

        try:
            config_id = response.json().get("id")
        except Exception:
            config_id = None

        if not config_id:
            print(
                "Could not read config id from response; values not posted. Response: ",
                response.text,
            )

        return config_id

    def ensure_config(self, cfg):
        """
        Find-or-create a config, so re-running the test (or several
        concurrent users) never hits the backend's unique constraint on
        (name, datatarget).

        Returns a tuple (config_id, existing_values) where existing_values
        is the set of value strings already attached to that config.
        """
        existing = self.find_existing_config(cfg["name"], cfg["datatarget"])

        if existing:
            existing_values = {
                v["value"] for v in existing.get("accountinfo_values", []) or []
            }
            return existing.get("id"), existing_values

        return self.create_config(cfg), set()

    def create_value(self, config_id, value):
        """
        Attach a value to a config.
        """
        payload = {
            "accountinfo_config": config_id,
            "value": value,
        }
        response = self.client.post(
            "/accountinfo/value/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if response.status_code not in (200, 201):
            try:
                error_msg = response.json().get("error", response.text)
            except Exception:
                error_msg = response.text
            print(
                "An error occured when attempt to POST admindata value : ",
                error_msg,
            )

    # ==========================
    # TASK
    # ==========================
    @task
    def post_admindata_config(self):
        """
        Ensure the reference admindata configs/values exist.

        For each entry, the config is only created if it doesn't already
        exist (matched on name + datatarget, unique on the backend); if it
        does, its id is reused and only the values missing from it are
        injected. This makes the task idempotent across several locust
        runs and safe with several concurrent users.
        """
        if not self.token:
            print("Token not available, request not executed")
            return

        global ADMINDATA_INITIALIZED

        with ADMINDATA_LOCK:
            if ADMINDATA_INITIALIZED:
                return

            data = [
                # ASSET
                {
                    "config": {
                        "name": "TAG",
                        "description": "Asset TAG",
                        "datatype": "TEXT",
                        "datatarget": "ASSET",
                    },
                    "values": None,
                },
                {
                    "config": {
                        "name": "Type",
                        "description": "Asset type",
                        "datatype": "SELECT",
                        "datatarget": "ASSET",
                    },
                    "values": [
                        {"value": "Desktop"},
                        {"value": "Laptop"},
                        {"value": "Server"},
                        {"value": "Virtual Machine"},
                        {"value": "Tablet"},
                        {"value": "Smartphone"},
                    ],
                },
                {
                    "config": {
                        "name": "Is active ?",
                        "description": "Asset is active or not",
                        "datatype": "CHECKBOX",
                        "datatarget": "ASSET",
                    },
                    "values": [{"value": "Yes"}, {"value": "No"}],
                },
                {
                    "config": {
                        "name": "Location",
                        "description": "Asset location",
                        "datatype": "SELECT",
                        "datatarget": "ASSET",
                    },
                    "values": [{"value": site["city"]} for site in SITES],
                },
                # IPD
                {
                    "config": {
                        "name": "TAG",
                        "description": "Device TAG",
                        "datatype": "TEXT",
                        "datatarget": "IPDISCOVER",
                    },
                    "values": None,
                },
                {
                    "config": {
                        "name": "Type",
                        "description": "Device type",
                        "datatype": "SELECT",
                        "datatarget": "IPDISCOVER",
                    },
                    "values": [{"value": "Printer"}, {"value": "Switch"}, {"value": "Server"}],
                },
                {
                    "config": {
                        "name": "Internal or external ?",
                        "description": "Device is internal or external",
                        "datatype": "CHECKBOX",
                        "datatarget": "IPDISCOVER",
                    },
                    "values": [{"value": "Internal"}, {"value": "External"}],
                },
            ]

            for item in data:
                cfg = item["config"]
                values = item["values"]

                config_id, existing_values = self.ensure_config(cfg)

                if not config_id or not values:
                    continue

                for v in values:
                    if v["value"] in existing_values:
                        continue
                    self.create_value(config_id, v["value"])

            ADMINDATA_INITIALIZED = True


# ==========================
# END-OF-RUN FLEET-WIDE ADMIN DATA GENERATION
# ==========================
# Requirement: instead of assigning admin data per-user during the run,
# do it ONCE at the very end, over the whole fleet of assets present on
# the test platform, and re-generate it (overwrite) on every run so
# re-running the test doesn't just pile up rows.
#
# This runs outside of any HttpUser (it needs to see every asset, not a
# random subset), so it uses the small `common.batch_client.BatchUser`
# shim instead of Locust's HttpSession.


def _random_tag(asset_id, site_code, type_value):
    code = TAG_TYPE_CODES.get(type_value, "AST")
    return f"{site_code}-{code}-{asset_id:05d}"


def _fetch_configs(client, headers, datatarget):
    """
    Fetch the configs for one accountinfo datatarget (ASSET or
    IPDISCOVER) with their possible values, keyed by config name.
    """
    response = client.get(
        "/accountinfo/config/",
        headers=headers,
        params={"datatarget": datatarget, "expand": "accountinfo_values"},
    )

    if response.status_code != 200:
        print("Could not fetch admindata configs for the fleet job : ", response.text)
        return {}

    try:
        results = response.json()
    except Exception:
        return {}

    if isinstance(results, dict):
        results = results.get("results", [])

    configs = {}
    for cfg in results:
        configs[cfg["name"]] = {
            "id": cfg["id"],
            "values": [
                {"id": v["id"], "value": v["value"]}
                for v in (cfg.get("accountinfo_values") or [])
            ],
        }
    return configs


def _fetch_all_assets(client, headers):
    """
    Fetch every asset ("tout le parc") currently on the platform.
    """
    response = client.get("/asset/bases/", headers=headers)

    if response.status_code != 200:
        print("Could not fetch assets for the fleet job : ", response.text)
        return []

    try:
        results = response.json()
    except Exception:
        return []

    # LimitOffsetPagination returns a plain list when no ?limit= is passed.
    if isinstance(results, dict):
        results = results.get("results", [])

    return results


def _fetch_all_netdevices(client, headers):
    """
    Fetch every IPDiscover device currently on the platform.
    """
    response = client.get("/netdevices/", headers=headers)

    if response.status_code != 200:
        print("Could not fetch netdevices for the fleet job : ", response.text)
        return []

    try:
        results = response.json()
    except Exception:
        return []

    if isinstance(results, dict):
        results = results.get("results", [])

    return results


def _find_existing_accountinfo_data(client, headers, object_slug, object_id):
    response = client.get(
        "/accountinfo/data/",
        headers=headers,
        params={"object_slug": object_slug, "object_id": object_id},
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


def _build_random_accountdata(configs, asset_id):
    """
    Build a random, business-representative accountdata payload for one
    asset: a TAG following a site/type naming convention, a Location
    consistent with that same site, a random asset Type, and a weighted
    "Is active ?" (most assets of a real fleet are active).
    """
    accountdata = {}

    # Pick ONE site per asset and reuse it for both TAG and Location, so
    # they never contradict each other (e.g. TAG "PAR-..." always maps to
    # Location "Paris").
    site = random.choice(SITES)

    # SELECT fields must be stored as {"value": <id>, "text": <label>},
    # NOT a bare id: that's the shape the frontend's <v-select> actually
    # writes (it has no `:reduce`, so its v-model is the whole option
    # object), and the only shape the backend's accountinfo-resolution
    # branch (asset/inventory_base/serializers.py) recognizes to turn a
    # SELECT value back into its label - a bare id falls through
    # unresolved and is displayed as-is. CHECKBOX is different: BootstrapVue's
    # b-form-checkbox-group stores a plain list of option ids, which is what
    # "Is active ?" below already sends.
    type_cfg = configs.get("Type")
    chosen_type = None
    if type_cfg and type_cfg["values"]:
        chosen_type = random.choice(type_cfg["values"])
        accountdata[str(type_cfg["id"])] = {
            "value": chosen_type["id"],
            "text": chosen_type["value"],
        }

    tag_cfg = configs.get("TAG")
    if tag_cfg:
        accountdata[str(tag_cfg["id"])] = _random_tag(
            asset_id, site["code"], chosen_type["value"] if chosen_type else None
        )

    location_cfg = configs.get("Location")
    if location_cfg and location_cfg["values"]:
        chosen_location = next(
            (v for v in location_cfg["values"] if v["value"] == site["city"]), None
        ) or random.choice(location_cfg["values"])
        accountdata[str(location_cfg["id"])] = {
            "value": chosen_location["id"],
            "text": chosen_location["value"],
        }

    active_cfg = configs.get("Is active ?")
    if active_cfg and active_cfg["values"]:
        weights = [9 if v["value"] == "Yes" else 1 for v in active_cfg["values"]]
        chosen_active = random.choices(active_cfg["values"], weights=weights, k=1)[0]
        accountdata[str(active_cfg["id"])] = [chosen_active["id"]]

    return accountdata


def _infer_device_type(netname, type_values):
    """
    Guess a device's "Type" from its netname (set by ipd_netgroup.py /
    ipd_netdevice.py as e.g. "PAR-LAN-SWITCH-01" or "Device 00042") when
    it plainly names one of the possible values, so a switch's admin data
    actually says "Switch" instead of a coin-flip between Switch/Printer/
    Server. Falls back to None (caller rolls a random value) otherwise.
    """
    netname_upper = (netname or "").upper()
    for value in type_values:
        if value["value"].upper() in netname_upper:
            return value
    return None


def _build_random_ipdiscover_accountdata(configs, netdevice):
    """
    Build a random, business-representative accountdata payload for one
    IPDiscover device: a TAG reusing its own netname, a Type inferred
    from that netname when possible, and a weighted "Internal or
    external ?" (a demo fleet behind netgroups/networks we made up is
    overwhelmingly internal equipment).
    """
    accountdata = {}

    type_cfg = configs.get("Type")
    if type_cfg and type_cfg["values"]:
        chosen_type = _infer_device_type(
            netdevice.get("netname"), type_cfg["values"]
        ) or random.choice(type_cfg["values"])
        accountdata[str(type_cfg["id"])] = {
            "value": chosen_type["id"],
            "text": chosen_type["value"],
        }

    tag_cfg = configs.get("TAG")
    if tag_cfg:
        accountdata[str(tag_cfg["id"])] = netdevice.get("netname") or (
            f"DEV-{netdevice['id']:05d}"
        )

    internal_cfg = configs.get("Internal or external ?")
    if internal_cfg and internal_cfg["values"]:
        weights = [9 if v["value"] == "Internal" else 1 for v in internal_cfg["values"]]
        chosen_internal = random.choices(internal_cfg["values"], weights=weights, k=1)[0]
        accountdata[str(internal_cfg["id"])] = [chosen_internal["id"]]

    return accountdata


def _upsert_accountinfo_data(client, headers, object_slug, object_id, accountdata):
    """
    Regenerate the admin data of one object (asset or netdevice):
    overwrite it if it already exists (so re-running the test refreshes
    the random values instead of piling up duplicate rows), create it
    otherwise.

    Returns "created", "updated" or "error", so the caller can report
    progress/a summary.
    """
    existing = _find_existing_accountinfo_data(client, headers, object_slug, object_id)

    payload = {
        "object_id": object_id,
        "object_slug": object_slug,
        "accountdata": accountdata,
    }

    if existing:
        response = client.patch(
            f"/accountinfo/data/{existing['id']}/",
            headers=headers,
            data=json.dumps(payload),
        )
        outcome = "updated"
    else:
        response = client.post(
            "/accountinfo/data/",
            headers=headers,
            data=json.dumps(payload),
        )
        outcome = "created"

    if response.status_code not in (200, 201):
        try:
            error_msg = response.json().get("error", response.text)
        except Exception:
            error_msg = response.text
        print(f"Error upserting admin data for {object_slug} {object_id} : ", error_msg)
        return "error"

    return outcome


def _progress_step(total):
    """
    Reporting interval that yields roughly 20 progress lines regardless
    of fleet size (at least every asset for small fleets, at most every
    200 for huge ones).
    """
    return max(1, min(200, total // 20 or 1))


def _regenerate_admindata_for(client, headers, label, object_slug, objects, build_accountdata):
    """
    Shared (re)generation loop for one object_slug: build + upsert random
    admin data for every object in `objects`, printing progress the same
    way for ASSET and IPDISCOVER.
    """
    total = len(objects)
    print(f"Regenerating admin data for {total} {label}(s)...")

    step = _progress_step(total)
    counts = {"created": 0, "updated": 0, "error": 0}

    for processed, obj in enumerate(objects, start=1):
        object_id = obj.get("id")
        if not object_id:
            continue

        accountdata = build_accountdata(obj)
        outcome = _upsert_accountinfo_data(client, headers, object_slug, object_id, accountdata)
        counts[outcome] += 1

        if processed % step == 0 or processed == total:
            pct = round(processed / total * 100) if total else 100
            print(
                f"[admin data] {label} {processed}/{total} processed ({pct}%) - "
                f"{counts['created']} created, {counts['updated']} updated, "
                f"{counts['error']} error(s)"
            )

    print(
        f"{label} admin data regeneration completed : {counts['created']} created, "
        f"{counts['updated']} updated, {counts['error']} error(s) out of {total}."
    )


@events.test_stop.add_listener
def regenerate_fleet_admindata(environment, **kwargs):
    """
    Runs once, when the load test stops : (re)generates admin data with
    random values for every asset (TAG / Type / Is active ? / Location)
    AND every IPDiscover device (TAG / Type / Internal or external ?) on
    the platform, so each run refreshes the whole fleet instead of
    relying on per-user, partial injection during the run.

    Guarded to run on the master (or local/non-distributed) process only,
    so it executes exactly once even with several worker processes.
    """
    if isinstance(environment.runner, WorkerRunner):
        return

    host = environment.host
    if not host:
        print("No host configured, skipping fleet admin data regeneration")
        return

    batch_user = BatchUser(host)
    token = Auth.get_token(batch_user)
    if not token:
        print("Fleet admin data regeneration skipped : authentication failed")
        return

    client = batch_user.client
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }

    asset_configs = _fetch_configs(client, headers, "ASSET")
    if not asset_configs:
        print("Asset admin data regeneration skipped : reference configs not found")
    else:
        assets = _fetch_all_assets(client, headers)
        _regenerate_admindata_for(
            client,
            headers,
            "asset",
            ASSET_OBJECT_SLUG,
            assets,
            lambda asset: _build_random_accountdata(asset_configs, asset["id"]),
        )

    ipdiscover_configs = _fetch_configs(client, headers, "IPDISCOVER")
    if not ipdiscover_configs:
        print("IPDiscover admin data regeneration skipped : reference configs not found")
    else:
        netdevices = _fetch_all_netdevices(client, headers)
        _regenerate_admindata_for(
            client,
            headers,
            "netdevice",
            IPDISCOVER_OBJECT_SLUG,
            netdevices,
            lambda netdevice: _build_random_ipdiscover_accountdata(ipdiscover_configs, netdevice),
        )
