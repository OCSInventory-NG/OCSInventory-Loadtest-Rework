import json
import random

from locust import HttpUser, events, task, between
from locust.runners import WorkerRunner

from common.auth import Auth
from common.batch_client import BatchUser
from common.users import ROLES, USERS, resolve_user_ids, set_user_ids

# Seeded on test_start rather than in a @task : asset_group.py and
# search_saved.py attribute what they create to one of these operators, and
# Locust gives no ordering guarantee between User classes. test_start fires
# before the first user is spawned, so the dependency disappears.
# Goes through common/batch_client.py so this setup traffic stays out of the
# load-test statistics.


def _headers(token):
    return {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }


def find_existing_group(client, headers, name):
    response = client.get("/groups/", headers=headers, params={"name": name})

    if response.status_code != 200:
        return None

    try:
        results = response.json()
    except Exception:
        return None

    if isinstance(results, dict):
        results = results.get("results", [])

    return next((g for g in results if g.get("name") == name), None)


def ensure_group(client, headers, name):
    existing = find_existing_group(client, headers, name)
    if existing:
        return existing.get("id")

    response = client.post(
        "/groups/", headers=headers, data=json.dumps({"name": name})
    )

    if response.status_code not in (200, 201):
        print("An error occured when attempt to POST group : ", response.text)
        return None

    try:
        return response.json().get("id")
    except Exception:
        return None


def find_existing_user(client, headers, username):
    response = client.get(
        "/users/", headers=headers, params={"username": username}
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


def ensure_user(client, headers, user_def, role_group_ids):
    existing = find_existing_user(client, headers, user_def["username"])
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
        "groups": (
            [role_group_ids[user_def["role"]]]
            if user_def["role"] in role_group_ids
            else []
        ),
    }
    response = client.post("/users/", headers=headers, data=json.dumps(payload))

    if response.status_code not in (200, 201):
        print("An error occured when attempt to POST user : ", response.text)
        return None

    try:
        return response.json().get("id")
    except Exception:
        return None


@events.test_start.add_listener
def provision_roster(environment, **kwargs):
    """
    Find-or-create every role/user of common/users.py, once, before the
    run starts, and publish the resulting ids for the other locustfiles.
    """
    if isinstance(environment.runner, WorkerRunner):
        return

    host = environment.host
    if not host:
        print("No host configured, skipping roster provisioning")
        return

    batch_user = BatchUser(host)
    token = Auth.get_token(batch_user)
    if not token:
        print("Roster provisioning skipped : authentication failed")
        return

    client = batch_user.client
    headers = _headers(token)

    role_group_ids = {}
    for role in ROLES:
        group_id = ensure_group(client, headers, role)
        if group_id:
            role_group_ids[role] = group_id

    for user_def in USERS:
        ensure_user(client, headers, user_def, role_group_ids)

    user_ids = resolve_user_ids(client, headers)
    set_user_ids(user_ids)

    print(
        f"Roster provisioned : {len(role_group_ids)}/{len(ROLES)} role(s), "
        f"{len(user_ids)}/{len(USERS)} account(s) available."
    )


class UserProvisioningAPITest(HttpUser):
    """
    Logs in as the demo accounts seeded above, so the platform sees genuine
    multi-operator auth traffic - this is what feeds the "user_login"
    automation trigger (see locustfiles/automation_setup.py).
    """

    wait_time = between(1, 5)
    token = None

    def on_start(self):
        self.token = Auth.get_token(self)

    @task
    def simulate_operator_login(self):
        user_def = random.choice(USERS)
        Auth.get_token(
            self, username=user_def["username"], password=user_def["password"]
        )
