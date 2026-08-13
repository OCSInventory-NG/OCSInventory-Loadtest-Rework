from locust import HttpUser, task, between
from common.auth import Auth
from common.users import ADMIN_USER_ID, get_user_ids, pick_owner_id
import json
import random
from gevent.lock import Semaphore

# ==========================
# GLOBAL SHARED STATE
# ==========================
GROUP_LOCK = Semaphore()

GROUP_IDS_BY_OS = {}
GROUP_CREATING = set()
GROUP_ASSETS_BY_OS = {}
STATIC_GROUPS_INITIALIZED = False

# Manually-curated ("static") groups a real admin would build by hand
# rather than via a saved search - fixed asset membership, not
# auto-refreshed. Shows off the visibility spectrum RestrictVisibility
# offers (every dynamic OS group above is "public" - these aren't).
STATIC_GROUPS = [
    {
        "name": "Postes a reformater",
        "description": "Selection manuelle de postes identifies pour reinstallation",
        "size": 5,
        "visibility": "private_personal",
    },
    {
        "name": "Machines VIP - Direction",
        "description": "Parc dedie aux comptes de direction, suivi prioritaire",
        "size": 4,
        "visibility": "private_group",
        "restrict_to_role": "Administrateurs IT",
    },
    {
        "name": "Parc pilote - nouvelle image",
        "description": "Echantillon de machines pour valider la prochaine image avant deploiement general",
        "size": 8,
        "visibility": "public",
    },
]


class AssetGroupAPITest(HttpUser):
    wait_time = between(1, 5)

    token = None
    user_ids = {}

    os_options = [
        "Windows",
        "Ubuntu",
        "Debian",
        "CentOS",
        "Fedora",
        "macOS",
    ]

    # ==========================
    # STARTUP
    # ==========================
    def on_start(self):
        self.token = Auth.get_token(self)
        if not self.token:
            return

        with GROUP_LOCK:
            for osname in self.os_options:
                GROUP_ASSETS_BY_OS.setdefault(osname, set())

        self.user_ids = get_user_ids(self.client, self._headers())

        for osname in self.os_options:
            self.ensure_group_for_os(osname)

        self.ensure_static_groups()

    # ==========================
    # HELPERS
    # ==========================
    def _headers(self):
        return {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
        }

    def ensure_group_for_os(self, osname: str):
        """
        Max ONE group per OS
        """

        with GROUP_LOCK:
            if osname in GROUP_IDS_BY_OS:
                return GROUP_IDS_BY_OS[osname]

            if osname in GROUP_CREATING:
                return None

            GROUP_CREATING.add(osname)

        group_name = f"Dummy {osname} group"
        group_id = self.find_group_id_by_name(group_name)

        if group_id is None:
            group_id = self.create_group_for_os(osname)

        with GROUP_LOCK:
            GROUP_CREATING.discard(osname)
            if group_id:
                GROUP_IDS_BY_OS[osname] = group_id
            return group_id

    def find_group_id_by_name(self, name: str):
        """
        Try to find existing group
        """
        r = self.client.get("/asset/groups/", headers=self._headers())
        if r.status_code != 200:
            return None

        for group in r.json():
            if group.get("name") == name:
                return group.get("id")

        return None

    def create_group_for_os(self, osname: str):
        """
        Create the group ONCE
        """
        search = [[{
            "object": "InventoryBase",
            "route": "asset/bases",
            "field": "osname",
            "fieldtype": "string",
            "operator": "istartswith",
            "value": osname,
            "link": "AND",
        }]]

        payload = {
            "visibility": "public",
            "allow_group_modification": False,
            "name": f"Dummy {osname} group",
            "description": "Dummy group for API test",
            "is_dynamic": True,
            "search": search,
            # Not pick_owner_id() : refresh_group_assets() keeps PATCHing
            # this group as admin, and only the creator may modify it.
            "user": ADMIN_USER_ID,
            "groups": [],
            "assets": [],
        }

        r = self.client.post(
            "/asset/groups/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if r.status_code not in (200, 201):
            print("Error creating group:", r.status_code, r.text)
            return None

        return r.json().get("id")

    def fetch_sample_asset_ids(self, size: int):
        """
        Grab up to `size` real asset ids to seed a static group's fixed
        membership with, instead of inventing ids that may not exist.
        """
        r = self.client.get(
            "/asset/bases/",
            headers=self._headers(),
            params={"limit": size},
            name="/asset/bases/?limit=[size]",
        )

        if r.status_code != 200:
            return []

        results = r.json()
        results = results.get("results", results) if isinstance(results, dict) else results
        return [a["id"] for a in results if a.get("id")]

    def find_role_group_id(self, role_name: str):
        """
        Look up one of the Django auth Groups seeded by
        locustfiles/user_provisioning.py, to scope a "private_group" static
        group's visibility to it. Returns None only if provisioning failed -
        the caller then falls back to "private_personal".
        """
        r = self.client.get(
            "/groups/",
            headers=self._headers(),
            params={"name": role_name},
            name="/groups/?name=[name]",
        )

        if r.status_code != 200:
            return None

        for group in r.json():
            if group.get("name") == role_name:
                return group.get("id")

        return None

    def find_static_group_id_by_name(self, name: str):
        r = self.client.get(
            "/asset/groups/",
            headers=self._headers(),
            params={"name": name},
            name="/asset/groups/?name=[name]",
        )

        if r.status_code != 200:
            return None

        for group in r.json():
            if group.get("name") == name:
                return group.get("id")

        return None

    def ensure_static_groups(self):
        """
        Find-or-create the fixed catalog of manually-curated groups
        (STATIC_GROUPS), once - fixed asset membership set at creation,
        never refreshed (that's what makes them "static", as opposed to
        the dynamic per-OS groups above).
        """
        global STATIC_GROUPS_INITIALIZED

        with GROUP_LOCK:
            if STATIC_GROUPS_INITIALIZED:
                return
            STATIC_GROUPS_INITIALIZED = True

        for group_def in STATIC_GROUPS:
            if self.find_static_group_id_by_name(group_def["name"]):
                continue

            payload = {
                "visibility": group_def["visibility"],
                "allow_group_modification": False,
                "name": group_def["name"],
                "description": group_def["description"],
                "is_dynamic": False,
                "search": None,
                "user": pick_owner_id(self.user_ids),
                "groups": [],
                "assets": self.fetch_sample_asset_ids(group_def["size"]),
            }

            restrict_to_role = group_def.get("restrict_to_role")
            if restrict_to_role:
                role_group_id = self.find_role_group_id(restrict_to_role)
                if role_group_id:
                    payload["groups"] = [role_group_id]
                else:
                    # Role not provisioned yet in this run - fall back to
                    # a visibility that doesn't need it.
                    payload["visibility"] = "private_personal"

            r = self.client.post(
                "/asset/groups/",
                headers=self._headers(),
                data=json.dumps(payload),
            )

            if r.status_code not in (200, 201):
                print("Error creating static group:", r.status_code, r.text)

    def search_assets_by_os(self, osname: str):
        """
        Get assets matching OS
        """
        search = [[{
            "object": "InventoryBase",
            "route": "asset/bases",
            "field": "osname",
            "fieldtype": "string",
            "operator": "istartswith",
            "value": osname,
            "link": "AND",
        }]]

        r = self.client.post(
            "/search/",
            headers=self._headers(),
            data=json.dumps({"search_data": search}),
        )

        if r.status_code not in (200, 201):
            print("Error searching assets:", r.status_code, r.text)
            return []

        return [a["id"] for a in r.json() if a.get("id")]

    def patch_group_assets(self, group_id: int, asset_ids):
        """
        Update assets list only
        """
        payload = {"assets": list(asset_ids)}

        r = self.client.patch(
            f"/asset/groups/{group_id}/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if r.status_code not in (200, 204):
            print("Error updating assets:", r.status_code, r.text)

    # ==========================
    # TASK
    # ==========================
    @task
    def refresh_group_assets(self):
        """
        Periodically update assets for ONE OS
        """
        if not self.token:
            return

        osname = random.choice(self.os_options)

        with GROUP_LOCK:
            group_id = GROUP_IDS_BY_OS.get(osname)

        if not group_id:
            return

        asset_ids = set(self.search_assets_by_os(osname))

        with GROUP_LOCK:
            if asset_ids == GROUP_ASSETS_BY_OS[osname]:
                return
            GROUP_ASSETS_BY_OS[osname] = asset_ids

        self.patch_group_assets(group_id, asset_ids)
