from locust import HttpUser, task, between
from common.auth import Auth
import json
import random


class NetdeviceAPITest(HttpUser):
    """
    Simulates ongoing IPDiscover scan traffic : creates extra netdevices
    on top of the fixed topology seeded by locustfiles/ipd_netgroup.py.
    """

    wait_time = between(1, 5)
    token = None
    networks = None
    netdevices = None

    def on_start(self):
        """
        Retrieve auth token at startup, then fetch the available networks
        right away so post_netdevice doesn't have to wait for get_network
        to be picked at random first.
        """
        self.token = Auth.get_token(self)
        if self.token:
            self.refresh_networks()

    def refresh_networks(self):
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

    def generate_mac_address(self):
        """Generate a realistic MAC address"""
        return ":".join([f"{random.randint(0, 255):02x}" for _ in range(6)])

    @task(10)
    def post_netdevice(self):
        """
        POST /netdevices/
        """
        if self.token:
            if not self.networks:
                print("No network available for netdevice creation")
                return
            
            # Génère un identifiant numérique entre 00001 et 99999 pour le nom
            random_number = f"{random.randint(1, 99999):05}"

            # Choisit un network aléatoire parmi ceux disponibles
            random_network = random.choice(self.networks)
            network_id = random_network["id"]

            # Génère une IP à partir du netid du network (supposé être de la forme X.Y.Z.0)
            netid = random_network.get("netid", "")
            try:
                oct1, oct2, oct3, _ = netid.split(".")
                # hôte entre 1 et 254 pour éviter .0 (réseau) et .255 (broadcast)
                host_octet = random.randint(1, 254)
                ip = f"{oct1}.{oct2}.{oct3}.{host_octet}"
            except ValueError:
                # Si le netid est mal formé, on log et on abandonne la création
                print(f"Invalid netid for network {network_id}: {netid}")
                return

            # Préparation des données avec incrémentation dynamique
            data = {
                "ip": ip,
                "netname": f"Device {random_number}",
                "mac": self.generate_mac_address(),
                "network": network_id
            }

            # Sending the POST request with the authentication token
            response = self.client.post(
                "/netdevices/",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(data),
            )

            if response.status_code not in (200, 201):
                print(
                    "An error occured when attempt to POST netdevices : ", response.text
                )

        else:
            print("Token not available, request not executed")

    @task
    def get_network(self):
        """
        GET /networks/ (keeps the network list fresh during the run)
        """
        if self.token:
            self.refresh_networks()
        else:
            print("Token not available, request not executed")

