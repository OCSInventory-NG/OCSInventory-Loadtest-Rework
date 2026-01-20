from locust import HttpUser, task, between
from common.auth import Auth
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


class AssetGroupAPITest(HttpUser):
    wait_time = between(1, 5)

    token = None

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

        for osname in self.os_options:
            self.ensure_group_for_os(osname)

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
            "user": 1,
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
            data=json.dumps(search),
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
