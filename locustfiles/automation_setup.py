import json

from locust import HttpUser, task, between
from gevent.lock import Semaphore

from common.auth import Auth

# ==========================
# GLOBAL SHARED STATE
# ==========================
AUTOMATION_LOCK = Semaphore()
AUTOMATION_INITIALIZED = False

# Scheduled jobs a real admin would configure (recurring maintenance
# tasks) - Scheduler.date/History.date are auto_now, so every seeded
# History row below timestamps at seed time rather than spread over real
# past runs; still populates the automation dashboard with something
# instead of nothing.
SCHEDULERS = [
    {
        "name": "Generation des donnees d'administration",
        "description": "Regenere les admin data (TAG, type, localisation) pour tout le parc",
        "recurrence": "daily",
        "hour": "02:00:00",
        "history": [
            (0, "Execution terminee avec succes : 401 asset(s) traites."),
            (0, "Execution terminee avec succes : 405 asset(s) traites."),
        ],
    },
    {
        "name": "Scan reseau IPDiscover",
        "description": "Lance un scan nmap sur les sous-reseaux configures",
        "recurrence": "weekly",
        "day_of_week": 1,
        "hour": "03:00:00",
        "history": [
            (0, "Scan termine : 17 reseau(x) traites."),
            (1, "Echec : nmap introuvable sur l'hote d'execution."),
        ],
    },
    {
        "name": "Nettoyage des journaux anciens",
        "description": "Purge les entrees d'historique asset de plus de 180 jours",
        "recurrence": "monthly",
        "day_of_month": 1,
        "hour": "04:00:00",
        "history": [
            (0, "Nettoyage termine avec succes."),
        ],
    },
]

# Rule engine showcase (automation/rule/) - see
# automation/rule/logic.py::Logic for exactly how these are evaluated
# and applied. Kept to 3 rules, each demonstrating a different mechanic:
#   - a plain field "set" on the triggering instance itself
#   - the AccountinfoConfig special case (writes into accountdata JSON)
#   - the user_login group-buffering mechanic (adds a "rule"-sourced
#     Group membership, distinct from the "manual" one users get at
#     creation - see user/serializers.py's group_assignments)
ACTIVE_ACCOUNTS_GROUP = "Comptes actifs"

INVENTORY_RULE = {
    "description": "Marquer les serveurs a la reception d'inventaire",
    "trigger": "inventory_received",
    "logic": {"in": ["Server", {"var": "osname"}]},
    "action": {
        "name": "Marquage serveur",
        "field": "description",
        "value": "Serveur - supervision renforcee",
    },
}

NETDEVICE_RULE = {
    "description": "Classer en interne les equipements decouverts sur les reseaux salle serveurs",
    "trigger": "netdevice_received",
    "logic": {"in": ["SRV", {"var": "network.nettag"}]},
    # Filled in at seed time once we know the real ids of the IPDISCOVER
    # "Internal or external ?" config/value (see config_admindata.py -
    # same accountinfo configs it creates).
}

LOGIN_RULE = {
    "description": "Suivre les comptes actifs a chaque connexion",
    "trigger": "user_login",
    # Always true: every login matches, so every user ends up in the
    # tracking group - see Logic.should_buffer_group_action/finalize_user_login_groups.
    "logic": {"!!": [1]},
    "action": {
        "name": "Suivi de connexion",
        "field": "groups",
        # "value" filled in at seed time with ACTIVE_ACCOUNTS_GROUP's id.
    },
}


class AutomationSetupAPITest(HttpUser):
    """
    Seeds the automation section of the demo, once: a few Scheduler
    entries with History rows, and 3 Rule/Action pairs covering the 3
    trigger types (inventory_received / netdevice_received / user_login)
    the engine supports.
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

    # --- Scheduler / History ---

    def find_existing_scheduler(self, name):
        response = self.client.get(
            "/automation/scheduler/",
            headers=self._headers(),
            params={"name": name},
            name="/automation/scheduler/?name=[name]",
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

    def ensure_scheduler(self, scheduler_def):
        existing = self.find_existing_scheduler(scheduler_def["name"])
        if existing:
            return existing.get("id")

        payload = {
            "name": scheduler_def["name"],
            "description": scheduler_def["description"],
            "active": True,
            "recurrence": scheduler_def["recurrence"],
            "hour": scheduler_def["hour"],
            "day_of_week": scheduler_def.get("day_of_week"),
            "day_of_month": scheduler_def.get("day_of_month"),
        }
        response = self.client.post(
            "/automation/scheduler/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if response.status_code not in (200, 201):
            print("An error occured when attempt to POST scheduler : ", response.text)
            return None

        try:
            return response.json().get("id")
        except Exception:
            return None

    def create_history(self, scheduler_id, status, comment):
        payload = {"scheduler": scheduler_id, "status": status, "comment": comment}
        response = self.client.post(
            "/automation/history/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if response.status_code not in (200, 201):
            print("An error occured when attempt to POST history : ", response.text)

    # --- Rule / Action ---

    def find_existing_rule(self, description, trigger):
        response = self.client.get(
            "/automation/rule/",
            headers=self._headers(),
            params={"description": description, "trigger": trigger},
            name="/automation/rule/?description=[description]&trigger=[trigger]",
        )

        if response.status_code != 200:
            return None

        try:
            results = response.json()
        except Exception:
            return None

        if isinstance(results, dict):
            results = results.get("results", [])

        return next((r for r in results if r.get("description") == description), None)

    def ensure_rule(self, rule_def):
        """
        Create the Rule with an empty "actions" list - despite the field
        being marked required, DRF's auto-generated PrimaryKeyRelatedField
        for this reverse relation accepts [] fine (RuleSerializer.create()
        only touches it in a loop, which a no-op on an empty list) -
        actions are attached afterwards via their own endpoint, same
        2-step pattern ipd_netgroup.py uses for networks/netdevices.
        """
        existing = self.find_existing_rule(rule_def["description"], rule_def["trigger"])
        if existing:
            return existing.get("id")

        payload = {
            "trigger": rule_def["trigger"],
            "enabled": True,
            "break_on_match": False,
            "description": rule_def["description"],
            "logic": rule_def["logic"],
            "actions": [],
        }
        response = self.client.post(
            "/automation/rule/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if response.status_code not in (200, 201):
            print("An error occured when attempt to POST rule : ", response.text)
            return None

        try:
            return response.json().get("id")
        except Exception:
            return None

    def create_action(self, rule_id, action_def, object_slug=None, object_id=None):
        if not rule_id:
            return

        payload = {
            "rule": rule_id,
            "action": "set",
            "name": action_def["name"],
            "field": action_def["field"],
            "value": action_def["value"],
        }
        if object_slug:
            payload["object_slug"] = object_slug
            payload["object_id"] = object_id

        response = self.client.post(
            "/automation/action/",
            headers=self._headers(),
            data=json.dumps(payload),
        )

        if response.status_code not in (200, 201):
            print("An error occured when attempt to POST rule action : ", response.text)

    # --- rule-specific lookups ---

    def find_ipdiscover_internal_value_id(self):
        """
        The IPDISCOVER "Internal or external ?" config (seeded by
        config_admindata.py) and its "Internal" value, looked up by name
        since ids are assigned by the backend at creation time.
        """
        response = self.client.get(
            "/accountinfo/config/",
            headers=self._headers(),
            params={"datatarget": "IPDISCOVER", "expand": "accountinfo_values"},
        )

        if response.status_code != 200:
            return None, None

        try:
            configs = response.json()
        except Exception:
            return None, None

        if isinstance(configs, dict):
            configs = configs.get("results", [])

        for cfg in configs:
            if cfg.get("name") == "Internal or external ?":
                internal_value = next(
                    (v for v in cfg.get("accountinfo_values", []) if v["value"] == "Internal"),
                    None,
                )
                return cfg["id"], internal_value["id"] if internal_value else None

        return None, None

    def find_or_create_group(self, name):
        response = self.client.get(
            "/groups/",
            headers=self._headers(),
            params={"name": name},
            name="/groups/?name=[name]",
        )

        if response.status_code == 200:
            existing = next((g for g in response.json() if g.get("name") == name), None)
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

    # ==========================
    # TASK
    # ==========================
    @task
    def seed_automation(self):
        """
        Find-or-create the scheduler/history rows and the 3 demo rules,
        once.
        """
        if not self.token:
            print("Token not available, request not executed")
            return

        global AUTOMATION_INITIALIZED

        with AUTOMATION_LOCK:
            if AUTOMATION_INITIALIZED:
                return

            for scheduler_def in SCHEDULERS:
                scheduler_id = self.ensure_scheduler(scheduler_def)
                if not scheduler_id:
                    continue
                for status, comment in scheduler_def["history"]:
                    self.create_history(scheduler_id, status, comment)

            # Rule 1 : inventory_received -> set description on the asset itself.
            rule_id = self.ensure_rule(INVENTORY_RULE)
            self.create_action(rule_id, INVENTORY_RULE["action"])

            # Rule 2 : netdevice_received -> set the IPDISCOVER "Internal or
            # external ?" accountinfo value via the AccountinfoConfig special case.
            config_id, internal_value_id = self.find_ipdiscover_internal_value_id()
            if config_id and internal_value_id:
                rule_id = self.ensure_rule(NETDEVICE_RULE)
                action_def = {
                    "name": "Classement Interne",
                    "field": f"accountdata:{config_id}",
                    "value": [internal_value_id],
                }
                self.create_action(
                    rule_id,
                    action_def,
                    object_slug="accountinfo.accountinfoconfig",
                    object_id=config_id,
                )
            else:
                print(
                    "Netdevice rule skipped : IPDISCOVER 'Internal or external ?' "
                    "config not found yet (run config_admindata.py's seeding first)"
                )

            # Rule 3 : user_login -> tag every account that logs in with a
            # "rule"-sourced (not manual) group membership.
            active_group_id = self.find_or_create_group(ACTIVE_ACCOUNTS_GROUP)
            if active_group_id:
                rule_id = self.ensure_rule(LOGIN_RULE)
                action_def = {**LOGIN_RULE["action"], "value": active_group_id}
                self.create_action(rule_id, action_def)

            AUTOMATION_INITIALIZED = True
