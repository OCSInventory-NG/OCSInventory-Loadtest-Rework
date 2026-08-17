from locust import HttpUser, task, between
from common.auth import Auth


class NetworkAPITest(HttpUser):
    """
    Read-only load on /networks/ and /netgroups/.

    Creation is handled once and deterministically by
    locustfiles/ipd_netgroup.py (fixed netgroup/network topology, checked
    for existence on every launch), so this class only exercises GET
    traffic against that seeded, stable data.
    """

    wait_time = between(1, 5)
    token = None
    networks = None
    netgroups = None

    def on_start(self):
        """
        Retrieve auth token at startup
        """
        self.token = Auth.get_token(self)

    @task
    def get_netgroup(self):
        """
        GET /netgroups/
        """
        if self.token:
            response = self.client.get(
                "/netgroups/", headers={"Authorization": f"Token {self.token}"}
            )

            if response.status_code in (200, 201):
                self.netgroups = response.json()
                netgroup_count = (
                    len(self.netgroups)
                    if isinstance(self.netgroups, list)
                    else self.netgroups.get("count", "Netgroups not available")
                )
                print(f"Number of retrieved netgroups : {netgroup_count}")
            else:
                print(
                    "An error occured when attempt to retrieve netgroup : ",
                    response.text,
                )
        else:
            print("Token not available, request not executed")

    @task
    def get_network(self):
        """
        GET /networks/
        """
        if self.token:
            response = self.client.get(
                "/networks/", headers={"Authorization": f"Token {self.token}"}
            )

            if response.status_code in (200, 201):
                self.networks = response.json()
                network_count = (
                    len(self.networks)
                    if isinstance(self.networks, list)
                    else self.networks.get("count", "Networks not available")
                )
                print(f"Number of retrieved networks : {network_count}")
            else:
                print(
                    "An error occured when attempt to retrieve network : ",
                    response.text,
                )
        else:
            print("Token not available, request not executed")
