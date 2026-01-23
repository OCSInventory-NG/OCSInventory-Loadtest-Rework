from locust import HttpUser, task, between
from common.auth import Auth
import json
import random


class NetworkAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None
    networks = None
    netgroups = None
    network_created = False

    def on_start(self):
        """
        Retrieve auth token at startup
        """
        self.token = Auth.get_token(self)

    @task
    def post_network(self):
        """
        POST /networks/
        """
        # Limite la création à 1 network par user Locust
        if self.network_created:
            return

        if self.token:
            # Génère un identifiant numérique entre 001 et 999 pour le nom
            random_number = f"{random.randint(1, 999):03}"

            # Génère un réseau IP aléatoire dans la plage privée 172.16.0.0/12
            # Exemple : 172.18.X.0
            second_octet = random.randint(16, 31)
            third_octet = random.randint(0, 255)
            netid = f"172.{second_octet}.{third_octet}.0"

            # Préparation des données avec incrémentation dynamique
            data = {
                "name": f"Network-{random_number}",
                "description": "Dummy network description",
                "netid": netid,
                "mask": "255.255.255.0",
                "group": None,
                "netdevices": []
            }

            # Sending the POST request with the authentication token
            response = self.client.post(
                "/networks/",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(data),
            )

            if response.status_code not in (200, 201):
                print(
                    "An error occured when attempt to POST networks : ", response.text
                )

            # Marque qu'un network a déjà été créé pour ce user
            self.network_created = True

        else:
            print("Token not available, request not executed")
    
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

    @task
    def patch_network(self):
        """
        PATCH /networks/{id}
        """
        if not self.networks:
            print("No network available for update")
            return

        if not self.netgroups:
            print("No netgroup available for network update")
            return

        if not self.token:
            print("Token not available, request not executed")
            return

        # Ne considère que les networks dont le group est nul
        networks_without_group = [
            network for network in self.networks if not network.get("group")
        ]

        if not networks_without_group:
            print("No network with group = null available for update")
            return

        random_networks = random.sample(
            networks_without_group, min(10, len(networks_without_group))
        )
        network_ids = [network["id"] for network in random_networks]

        # Sélectionne un netgroup aléatoire et utilise son id pour la mise à jour
        random_netgroup = random.choice(self.netgroups)
        netgroup_id = random_netgroup["id"]
        update_data = {"group": netgroup_id}

        for network_id in network_ids:
            response = self.client.patch(
                f"/networks/{network_id}/",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(update_data),
            )

            if response.status_code != 200:
                print(
                    f"An error occured when attempt to patch {network_id} : {response.text}"
                )

