from locust import HttpUser, task, between
from common.auth import Auth
import json


class AssetPackageAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None

    def on_start(self):
        # Retrieve auth token at startup
        self.token = Auth.get_token(self)

    @task
    def idle_task(self):
        pass
