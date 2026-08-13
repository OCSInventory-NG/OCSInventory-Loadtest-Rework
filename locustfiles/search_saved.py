import json

from locust import HttpUser, task, between
from gevent.lock import Semaphore

from common.auth import Auth
from common.users import get_user_ids, pick_owner_id

# ==========================
# GLOBAL SHARED STATE
# ==========================
SAVED_SEARCH_LOCK = Semaphore()
SAVED_SEARCH_INITIALIZED = False

# Named, reusable searches a real admin would bookmark instead of
# retyping - reuses the same query shapes asset_search.py already
# exercises ad-hoc, but persisted via /search/save/ this time.
SAVED_SEARCHES = [
    {
        "name": "Postes Windows",
        "description": "Tous les postes sous Windows (toutes versions)",
        "visibility": "public",
        "search": [
            [
                {
                    "object": "InventoryBase",
                    "route": "asset/bases",
                    "field": "osname",
                    "fieldtype": "string",
                    "operator": "istartswith",
                    "value": "Windows",
                    "link": "",
                }
            ]
        ],
    },
    {
        "name": "Parc Linux (Debian/Ubuntu)",
        "description": "Postes et serveurs sous Debian ou Ubuntu",
        "visibility": "public",
        "search": [
            [
                {
                    "object": "InventoryBase",
                    "route": "asset/bases",
                    "field": "osname",
                    "fieldtype": "string",
                    "operator": "icontains",
                    "value": "Debian",
                    "link": "",
                },
                {
                    "object": "InventoryBase",
                    "route": "asset/bases",
                    "field": "osname",
                    "fieldtype": "string",
                    "operator": "icontains",
                    "value": "Ubuntu",
                    "link": "OR",
                },
            ]
        ],
    },
    {
        "name": "Serveurs uniquement",
        "description": "Toutes machines dont le nom d'OS contient Server",
        "visibility": "public",
        "search": [
            [
                {
                    "object": "InventoryBase",
                    "route": "asset/bases",
                    "field": "osname",
                    "fieldtype": "string",
                    "operator": "icontains",
                    "value": "Server",
                    "link": "",
                }
            ]
        ],
    },
    {
        "name": "Postes non a jour",
        "description": "Postes n'ayant pas encore recu de mise a jour de collecte",
        "visibility": "private_personal",
        "search": [
            [
                {
                    "object": "InventoryBase",
                    "route": "asset/bases",
                    "field": "description",
                    "fieldtype": "string",
                    "operator": "iexact",
                    "value": "System not updated",
                    "link": "",
                }
            ]
        ],
    },
    {
        "name": "Audit - Postes macOS",
        "description": "Suivi du parc macOS pour la campagne d'audit",
        "visibility": "private_group",
        "restrict_to_role": "Auditeurs",
        "search": [
            [
                {
                    "object": "InventoryBase",
                    "route": "asset/bases",
                    "field": "osname",
                    "fieldtype": "string",
                    "operator": "icontains",
                    "value": "macOS",
                    "link": "",
                }
            ]
        ],
    },
]


class SavedSearchAPITest(HttpUser):
    """
    Seeds a handful of named/bookmarked searches (SAVED_SEARCHES) once,
    owned by a mix of the demo operator roster (common/users.py) with a
    mix of visibilities - public, private to their creator, and private
    to one role's Group - instead of every saved search being public and
    owned by admin.
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

    def find_existing_search(self, name):
        response = self.client.get(
            "/search/save/",
            headers=self._headers(),
            params={"name": name},
            name="/search/save/?name=[name]",
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

    def find_role_group_id(self, role_name):
        response = self.client.get(
            "/groups/",
            headers=self._headers(),
            params={"name": role_name},
            name="/groups/?name=[name]",
        )

        if response.status_code != 200:
            return None

        for group in response.json():
            if group.get("name") == role_name:
                return group.get("id")

        return None

    def create_search(self, search_def, user_ids):
        payload = {
            "name": search_def["name"],
            "description": search_def["description"],
            "search": search_def["search"],
            "visibility": search_def["visibility"],
            "allow_group_modification": False,
            "user": pick_owner_id(user_ids),
            "groups": [],
        }

        restrict_to_role = search_def.get("restrict_to_role")
        if restrict_to_role:
            role_group_id = self.find_role_group_id(restrict_to_role)
            if role_group_id:
                payload["groups"] = [role_group_id]
            else:
                # Role not provisioned yet in this run - fall back to a
                # visibility that doesn't depend on it.
                payload["visibility"] = "private_personal"

        response = self.client.post(
            "/search/save/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if response.status_code not in (200, 201):
            print(
                "An error occured when attempt to POST saved search : ",
                response.text,
            )

    # ==========================
    # TASK
    # ==========================
    @task
    def seed_saved_searches(self):
        """
        Find-or-create every entry in SAVED_SEARCHES, once.
        """
        if not self.token:
            print("Token not available, request not executed")
            return

        global SAVED_SEARCH_INITIALIZED

        with SAVED_SEARCH_LOCK:
            if SAVED_SEARCH_INITIALIZED:
                return

            user_ids = get_user_ids(self.client, self._headers())

            for search_def in SAVED_SEARCHES:
                if self.find_existing_search(search_def["name"]):
                    continue
                self.create_search(search_def, user_ids)

            SAVED_SEARCH_INITIALIZED = True
