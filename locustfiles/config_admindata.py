from locust import HttpUser, task, between
from common.auth import Auth
import json
from gevent.lock import Semaphore


class AdmindataAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None
    admindata = None
    _admindata_initialized = False
    _admindata_init_lock = Semaphore()

    def on_start(self):
        """
        Retrieve auth token at startup
        """
        self.token = Auth.get_token(self)

    @task
    def post_admindata_config(self):
        """
        POST /accountinfo/config/
        """
        if not self.token:
            print("Token not available, request not executed")
            return

        with self._admindata_init_lock:
            if self._admindata_initialized:
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
                    "values": [{"value": "Desktop"}, {"value": "Laptop"}, {"value": "Server"}],
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

            headers = {
                "Authorization": f"Token {self.token}",
                "Content-Type": "application/json",
            }

            for item in data:
                cfg = item["config"]
                values = item["values"]

                response = self.client.post(
                    "/accountinfo/config/",
                    headers=headers,
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
                    continue

                if not values:
                    continue

                try:
                    config_id = response.json().get("id")
                except Exception:
                    config_id = None

                if not config_id:
                    print(
                        "Could not read config id from response; values not posted. Response: ",
                        response.text,
                    )
                    continue

                for v in values:
                    payload = {
                        "accountinfo_config": config_id,
                        "value": v["value"],
                    }
                    resp_val = self.client.post(
                        "/accountinfo/value/",
                        headers=headers,
                        data=json.dumps(payload),
                    )

                    if resp_val.status_code not in (200, 201):
                        try:
                            error_msg = resp_val.json().get("error", resp_val.text)
                        except Exception:
                            error_msg = resp_val.text
                        print(
                            "An error occured when attempt to POST admindata value : ",
                            error_msg,
                        )

            self._admindata_initialized = True
