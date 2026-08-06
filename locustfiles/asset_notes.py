import json
import random

from locust import events
from locust.runners import WorkerRunner

from common.auth import Auth
from common.batch_client import BatchUser
from common.users import pick_owner_id, resolve_user_ids

# ==========================
# END-OF-RUN FLEET-WIDE ASSET NOTES
# ==========================
# Same rationale/pattern as config_admindata.py's regenerate_fleet_admindata
# and asset_log_history.py's generate_fleet_log_history: this needs to see
# every asset, not a random subset picked by whichever simulated user
# happens to touch it during the run, so it runs once at test_stop
# instead of as an HttpUser task.

ASSET_OBJECT_SLUG = "inventory_base.inventorybase"

# Not every asset in a real fleet has admin notes on it - only the ones
# someone actually had a reason to annotate.
NOTE_PROBABILITY = 0.15

NOTE_CATALOG = [
    "RAM portee a 16 Go suite a une demande utilisateur.",
    "Disque dur remplace suite a une alerte SMART.",
    "Reinstallation complete du poste apres incident (voir ticket support).",
    "Machine identifiee comme obsolete - a prevoir au prochain plan de renouvellement.",
    "Poste prete temporairement, restitution prevue en fin de mission.",
    "Blocage des ports USB applique suite a la politique de securite du site.",
    "Intervention recurrente sur ce poste, cause non identifiee - a surveiller.",
    "Changement de bureau de l'utilisateur, poste redeploye sur le nouveau site.",
    "Carte reseau remplacee suite a des deconnexions repetees.",
    "Poste place sous garantie constructeur etendue jusqu'a l'annee prochaine.",
]

# A given asset gets 1 note most of the time, occasionally 2.
NOTE_COUNTS = [1, 2]
NOTE_COUNT_WEIGHTS = [8, 2]


def _fetch_all_assets(client, headers):
    """
    Fetch every asset ("tout le parc") currently on the platform.
    """
    response = client.get("/asset/bases/", headers=headers)

    if response.status_code != 200:
        print("Could not fetch assets for the notes job : ", response.text)
        return []

    try:
        results = response.json()
    except Exception:
        return []

    if isinstance(results, dict):
        results = results.get("results", [])

    return results


def _post_note(client, headers, asset_id, text, creator_id):
    payload = {
        "text": text,
        "creator": creator_id,
        "object_slug": ASSET_OBJECT_SLUG,
        "object_id": asset_id,
    }
    response = client.post("/notes/", headers=headers, data=json.dumps(payload))

    if response.status_code not in (200, 201):
        try:
            error_msg = response.json().get("error", response.text)
        except Exception:
            error_msg = response.text
        print(f"Error posting note for asset {asset_id} : ", error_msg)
        return False

    return True


def _progress_step(total):
    return max(1, min(200, total // 20 or 1))


@events.test_stop.add_listener
def generate_fleet_notes(environment, **kwargs):
    """
    Runs once, when the load test stops : adds a plausible admin note to
    a random subset of the fleet (NOTE_PROBABILITY), each attributed to a
    random demo operator (common/users.py).

    Deliberately additive, NOT find-or-create : a note is a standalone
    annotation, and a real fleet keeps accumulating them over time, so
    each run adds more instead of overwriting anything - same rationale
    as asset_log_history.py.

    Guarded to run on the master (or local/non-distributed) process only,
    so it executes exactly once even with several worker processes.
    """
    if isinstance(environment.runner, WorkerRunner):
        return

    host = environment.host
    if not host:
        print("No host configured, skipping fleet notes generation")
        return

    batch_user = BatchUser(host)
    token = Auth.get_token(batch_user)
    if not token:
        print("Fleet notes generation skipped : authentication failed")
        return

    client = batch_user.client
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }

    user_ids = resolve_user_ids(client, headers)

    assets = _fetch_all_assets(client, headers)
    total = len(assets)
    print(f"Generating notes for up to {total} asset(s)...")

    step = _progress_step(total)
    posted = 0
    annotated = 0

    for processed, asset in enumerate(assets, start=1):
        asset_id = asset.get("id")
        if asset_id and random.random() <= NOTE_PROBABILITY:
            annotated += 1
            note_count = random.choices(NOTE_COUNTS, weights=NOTE_COUNT_WEIGHTS, k=1)[0]
            for text in random.sample(NOTE_CATALOG, min(note_count, len(NOTE_CATALOG))):
                if _post_note(client, headers, asset_id, text, pick_owner_id(user_ids)):
                    posted += 1

        if processed % step == 0 or processed == total:
            pct = round(processed / total * 100) if total else 100
            print(
                f"[notes] {processed}/{total} asset(s) processed ({pct}%) - "
                f"{annotated} annotated, {posted} note(s) posted"
            )

    print(
        f"Fleet notes generation completed : {posted} note(s) posted across "
        f"{annotated} asset(s) out of {total}."
    )
