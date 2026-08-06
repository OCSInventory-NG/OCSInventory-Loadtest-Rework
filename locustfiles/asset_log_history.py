import json
import random

from locust import events
from locust.runners import WorkerRunner

from common.auth import Auth
from common.batch_client import BatchUser

# ==========================
# END-OF-RUN FLEET-WIDE LOG HISTORY GENERATION
# ==========================
# Objective: give every asset on the platform a plausible ("fake")
# history of server-side interactions on /asset/logs/, instead of the
# handful of random scopes asset_collection.py's post_asset_log task
# happens to hit on a random subset of assets during the run.
#
# This runs outside of any HttpUser (it needs to see every asset, not a
# random subset), triggered once when the test stops - same approach as
# config_admindata.py's regenerate_fleet_admindata.

ASSET_OBJECT_SLUG = "inventory_base.inventorybase"

# Each entry is (scope, comment, probability) : not every asset gets
# every event, so the fleet ends up with an uneven, believable-looking
# history instead of identical clones. `scope` values match the
# backend's asset.log.Log.SCOPE_CHOICES exactly.
LOG_STORYLINE = [
    ("INVENTORY_BASE_INSERT", "Premiere remontee d'inventaire recue par le serveur.", 1.0),
    ("INVENTORY_EXT_INSERT", "Inventaire etendu initial enregistre.", 0.9),
    ("CONFIG_UPDATE", "Configuration de collecte mise a jour sur le poste.", 0.6),
    ("INVENTORY_BASE_UPDATE", "Inventaire de base mis a jour lors du dernier check-in agent.", 1.0),
    ("INVENTORY_EXT_UPDATE", "Inventaire etendu mis a jour lors du dernier check-in agent.", 0.8),
    ("TEMPLATE_UPDATE", "Modele de collecte applique avec succes.", 0.3),
    ("DEPLOYMENT_ACK", "Accuse de reception d'un deploiement logiciel.", 0.25),
    ("DEPLOYMENT_ERR", "Echec du deploiement logiciel sur le poste.", 0.08),
    ("INVENTORY_BASE_ERR", "Erreur lors du traitement de l'inventaire de base (format invalide).", 0.05),
    ("INVENTORY_EXT_ERR", "Erreur lors du traitement de l'inventaire etendu.", 0.05),
    ("CONFIG_ERR", "Echec de l'application de la configuration.", 0.04),
    ("TEMPLATE_ERR", "Echec de l'application du modele de collecte.", 0.04),
]

# Number of log rows posted per HTTP call (asset.log.Log's create()
# accepts a JSON array), to avoid one round-trip per asset on a large
# fleet.
LOG_BATCH_SIZE = 200


def _build_asset_history(asset_id):
    """
    Roll the storyline for one asset : each event is included
    independently based on its probability.
    """
    entries = []
    for scope, comment, probability in LOG_STORYLINE:
        if random.random() <= probability:
            entries.append({"asset": asset_id, "scope": scope, "comment": comment})
    return entries


def _progress_step(total):
    """
    Reporting interval that yields roughly 20 progress lines regardless
    of fleet size (at least every asset for small fleets, at most every
    200 for huge ones).
    """
    return max(1, min(200, total // 20 or 1))


def _fetch_all_assets(client, headers):
    """
    Fetch every asset ("tout le parc") currently on the platform.
    """
    response = client.get("/asset/bases/", headers=headers)

    if response.status_code != 200:
        print("Could not fetch assets for the log history job : ", response.text)
        return []

    try:
        results = response.json()
    except Exception:
        return []

    # LimitOffsetPagination returns a plain list when no ?limit= is passed.
    if isinstance(results, dict):
        results = results.get("results", [])

    return results


def _post_log_batch(client, headers, batch):
    response = client.post(
        "/asset/logs/",
        headers=headers,
        data=json.dumps(batch),
    )

    if response.status_code not in (200, 201):
        try:
            error_msg = response.json().get("error", response.text)
        except Exception:
            error_msg = response.text
        print("Error posting asset log batch : ", error_msg)
        return False

    return True


@events.test_stop.add_listener
def generate_fleet_log_history(environment, **kwargs):
    """
    Runs once, when the load test stops : posts a plausible batch of
    "fake" interaction history to /asset/logs/ for every asset on the
    platform (inventory inserts/updates, occasional errors,
    template/config updates, deployment acknowledgements).

    Deliberately additive, NOT find-or-create : a log is a history, and a
    real fleet keeps accumulating log rows over time, so each run adds
    another batch of "activity" on top of the previous ones instead of
    overwriting anything.

    Guarded to run on the master (or local/non-distributed) process only,
    so it executes exactly once even with several worker processes.
    """
    if isinstance(environment.runner, WorkerRunner):
        return

    host = environment.host
    if not host:
        print("No host configured, skipping asset log history generation")
        return

    batch_user = BatchUser(host)
    token = Auth.get_token(batch_user)
    if not token:
        print("Asset log history generation skipped : authentication failed")
        return

    client = batch_user.client
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }

    assets = _fetch_all_assets(client, headers)
    total = len(assets)
    print(f"Generating log history for {total} asset(s)...")

    step = _progress_step(total)
    pending = []
    posted = 0
    failed_batches = 0

    for processed, asset in enumerate(assets, start=1):
        asset_id = asset.get("id")
        if asset_id:
            pending.extend(_build_asset_history(asset_id))

        if pending and (len(pending) >= LOG_BATCH_SIZE or processed == total):
            if _post_log_batch(client, headers, pending):
                posted += len(pending)
            else:
                failed_batches += 1
            pending = []

        if processed % step == 0 or processed == total:
            pct = round(processed / total * 100) if total else 100
            print(
                f"[log history] {processed}/{total} asset(s) processed ({pct}%) - "
                f"{posted} log(s) posted"
            )

    print(
        f"Asset log history generation completed : {posted} log(s) posted for "
        f"{total} asset(s) ({failed_batches} failed batch(es))."
    )
