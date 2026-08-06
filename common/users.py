"""
Static roster of demo operator accounts and roles.

Shared by locustfiles that need several distinct human actors instead of
having every group/saved search/note/login attributed to a single
hardcoded "admin" (or user id 1) - see locustfiles/user_provisioning.py,
which creates these once, and asset_group.py / search_saved.py /
asset_notes.py, which pick a random one to own what they create.
"""

import random

import gevent

# Django auth Groups (roles). Kept intentionally simple - no fine-grained
# permission wiring, just a name each user gets attached to so the demo
# shows a mix of profiles instead of a flat, undifferentiated user list.
ROLES = [
    "Helpdesk",
    "Techniciens",
    "Auditeurs",
    "Administrateurs IT",
    "Responsables de parc",
]

# One shared dummy password for every demo account - fine for a throwaway
# load-test target, never meant to be a real credential.
DEFAULT_PASSWORD = "Demo#2026!"

USERS = [
    {"username": "julien.dupont", "first_name": "Julien", "last_name": "Dupont", "role": "Helpdesk"},
    {"username": "marie.lefevre", "first_name": "Marie", "last_name": "Lefevre", "role": "Helpdesk"},
    {"username": "thomas.bernard", "first_name": "Thomas", "last_name": "Bernard", "role": "Techniciens"},
    {"username": "sophie.martin", "first_name": "Sophie", "last_name": "Martin", "role": "Techniciens"},
    {"username": "nicolas.petit", "first_name": "Nicolas", "last_name": "Petit", "role": "Techniciens"},
    {"username": "claire.moreau", "first_name": "Claire", "last_name": "Moreau", "role": "Auditeurs"},
    {"username": "antoine.girard", "first_name": "Antoine", "last_name": "Girard", "role": "Auditeurs"},
    {"username": "camille.roux", "first_name": "Camille", "last_name": "Roux", "role": "Administrateurs IT"},
    {"username": "lucas.fontaine", "first_name": "Lucas", "last_name": "Fontaine", "role": "Responsables de parc"},
]

for _user in USERS:
    _user.setdefault("email", f"{_user['username']}@ocsinventory-demo.local")
    _user.setdefault("password", DEFAULT_PASSWORD)


def resolve_user_ids(client, headers):
    """
    Look up the numeric id of every USERS roster entry currently on the
    platform via GET /users/.

    Returns a dict {username: id}, populated only for accounts that
    already exist server-side. Callers use this instead of importing any
    in-memory state from locustfiles/user_provisioning.py, since Locust
    gives no ordering guarantee across HttpUser classes: this file's
    seeding task may not have run yet in a given process/run.
    """
    response = client.get("/users/", headers=headers)
    if response.status_code != 200:
        return {}

    try:
        results = response.json()
    except Exception:
        return {}

    if isinstance(results, dict):
        results = results.get("results", [])

    wanted = {u["username"] for u in USERS}
    return {
        u["username"]: u["id"]
        for u in results
        if u.get("username") in wanted and u.get("id") is not None
    }


def resolve_user_ids_with_retry(client, headers, attempts=5, delay=2):
    """
    Same as resolve_user_ids, but retries a few times (gevent.sleep
    between attempts) before giving up.

    locustfiles/user_provisioning.py seeds the roster on its own
    schedule, and Locust gives no ordering guarantee across HttpUser
    classes - a bare one-shot lookup called from another file's on_start
    often runs before provisioning has had a chance to complete, and
    would silently fall back to admin ownership for the rest of the run.
    Use this instead of resolve_user_ids at any one-time seeding call
    site that wants real ownership diversity.
    """
    for attempt in range(attempts):
        user_ids = resolve_user_ids(client, headers)
        if user_ids:
            return user_ids
        if attempt < attempts - 1:
            gevent.sleep(delay)
    return {}


def pick_owner_id(user_ids, fallback=1):
    """
    Random demo-user id to attribute ownership/creation to, or `fallback`
    (admin, id 1 on a fresh platform) if the roster isn't seeded yet.
    """
    if not user_ids:
        return fallback
    return random.choice(list(user_ids.values()))
