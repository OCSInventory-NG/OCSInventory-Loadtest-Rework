import json
import random

from locust import HttpUser, task, between
from gevent.lock import Semaphore

from common.auth import Auth
from common.users import ROLES, USERS

# ==========================
# GLOBAL SHARED STATE
# ==========================
# Module-level (not class-level) so it is really shared across every
# simulated user of this process - see locustfiles/config_admindata.py
# for the same pattern and rationale.
PROVISIONING_LOCK = Semaphore()
PROVISIONING_INITIALIZED = False


class UserProvisioningAPITest(HttpUser):
    """
    Seeds the demo operator roster (common/users.py) once : one Django
    auth Group per role, one User per roster entry attached to their
    role's group. Other locustfiles (asset_group.py, search_saved.py,
    asset_notes.py, ...) then pick a random one of these to attribute
    what they create to, instead of everything being owned by admin.

    Also periodically logs in AS one of these accounts (their own
    username/password) so the platform sees genuine multi-operator auth
    traffic - this is what feeds the "user_login" automation trigger
    (see locustfiles/automation_setup.py) and gives login history/audit
    views more than one actor.
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

    def find_existing_group(self, name):
        response = self.client.get(
            "/groups/",
            headers=self._headers(),
            params={"name": name},
            name="/groups/?name=[name]",
        )

        if response.status_code != 200:
            return None

        try:
            results = response.json()
        except Exception:
            return None

        if isinstance(results, dict):
            results = results.get("results", [])

        return next((g for g in results if g.get("name") == name), None)

    def ensure_group(self, name):
        existing = self.find_existing_group(name)
        if existing:
            return existing.get("id")

        response = self.client.post(
            "/groups/",
            headers=self._headers(),
            data=json.dumps({"name": name}),
        )

        if response.status_code not in (200, 201):
            print("An error occured when attempt to POST group : ", response.text)
            return None

        try:
            return response.json().get("id")
        except Exception:
            return None

    def find_existing_user(self, username):
        response = self.client.get(
            "/users/",
            headers=self._headers(),
            params={"username": username},
            name="/users/?username=[username]",
        )

        if response.status_code != 200:
            return None

        try:
            results = response.json()
        except Exception:
            return None

        if isinstance(results, dict):
            results = results.get("results", [])

        return next((u for u in results if u.get("username") == username), None)

    def ensure_user(self, user_def, role_group_ids):
        existing = self.find_existing_user(user_def["username"])
        if existing:
            return existing.get("id")

        payload = {
            "username": user_def["username"],
            "password": user_def["password"],
            # email/first_name/last_name/is_superuser are optional per the
            # API schema but UserSerializer.create() indexes them directly
            # (validated_data["email"], ...) - omitting any of them 500s.
            "email": user_def["email"],
            "first_name": user_def["first_name"],
            "last_name": user_def["last_name"],
            "is_superuser": False,
            "groups": [role_group_ids[user_def["role"]]] if user_def["role"] in role_group_ids else [],
        }
        response = self.client.post(
            "/users/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if response.status_code not in (200, 201):
            print("An error occured when attempt to POST user : ", response.text)
            return None

        try:
            return response.json().get("id")
        except Exception:
            return None

    # ==========================
    # TASKS
    # ==========================
    @task
    def provision_roster(self):
        """
        Find-or-create every role/user in common/users.py, once.
        """
        if not self.token:
            print("Token not available, request not executed")
            return

        global PROVISIONING_INITIALIZED

        with PROVISIONING_LOCK:
            if PROVISIONING_INITIALIZED:
                return

            role_group_ids = {}
            for role in ROLES:
                group_id = self.ensure_group(role)
                if group_id:
                    role_group_ids[role] = group_id

            for user_def in USERS:
                self.ensure_user(user_def, role_group_ids)

            PROVISIONING_INITIALIZED = True

    @task
    def simulate_operator_login(self):
        """
        Log in as a random roster account (their own credentials), purely
        to generate real multi-operator auth traffic - triggers the
        backend's "user_login" post-login signal/rule engine for an
        account other than admin.
        """
        user_def = random.choice(USERS)
        Auth.get_token(self, username=user_def["username"], password=user_def["password"])
