import json

class Auth:
    @staticmethod
    def get_token(self, username="admin", password="admin"):
        """
        Retrieve token auth.

        Defaults to the admin/admin account so every existing call site
        (`Auth.get_token(self)`) keeps working unchanged; pass a specific
        username/password (see common/users.py) to authenticate as one of
        the demo operator accounts instead - see
        locustfiles/user_provisioning.py.
        """
        # User authentication
        response = self.client.post(
            "/api-auth/token",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"username": username, "password": password})
        )
        # Check token retrieval
        if response.status_code == 200:
            return response.json().get("token")
        else:
            print("Login failed : ", response.text)