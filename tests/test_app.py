import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from traffic_monitor import create_app


TEST_IMAGE_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAusB9Y9jv1QAAAAASUVORK5CYII="
)


class TrafficMonitorTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.app = create_app(
            {
                "TESTING": True,
                "BASE_DIR": root,
                "STATIC_DIR": root / "static",
                "UPLOAD_DIR": root / "static" / "uploads",
                "DB_PATH": root / "traffic_monitor.db",
                "DEFAULT_SPEED_LIMIT_KMH": 30.0,
                "PAYSTACK_SECRET_KEY": "sk_test_dummy",
                "PAYSTACK_PUBLIC_KEY": "pk_test_dummy",
                "APP_BASE_URL": "http://127.0.0.1:5000",
                "ADMIN_USERNAME": "admin",
                "ADMIN_PASSWORD": "secret123",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def post_event(self, node_id, timestamp, plate_text_override):
        return self.client.post(
            "/api/v1/log_event",
            json={
                "node_id": node_id,
                "timestamp": timestamp,
                "plate_text_override": plate_text_override,
                "plate_image_base64": TEST_IMAGE_B64,
            },
        )

    def admin_login(self):
        return self.client.post(
            "/admin/login",
            data={"username": "admin", "password": "secret123"},
            follow_redirects=False,
        )

    def test_speeding_vehicle_creates_ticket_and_blocks_gate(self):
        entry = self.post_event("A", 1000, "LAG123AA")
        self.assertEqual(entry.status_code, 201)
        self.assertEqual(entry.get_json()["status"], "RECORDED")

        exit_event = self.post_event("B", 1005, "LAG123AA")
        self.assertEqual(exit_event.status_code, 201)
        self.assertEqual(exit_event.get_json()["status"], "VIOLATION")
        ticket_id = exit_event.get_json()["ticket_id"]

        gate_check = self.client.get("/api/v1/check_ticket?plate=LAG123AA")
        self.assertEqual(gate_check.status_code, 200)
        self.assertEqual(gate_check.get_json()["status"], "DENY")

        pay_redirect = self.client.post(f"/api/v1/tickets/{ticket_id}/pay", follow_redirects=False)
        self.assertEqual(pay_redirect.status_code, 302)
        self.assertIn("/admin/login", pay_redirect.headers["Location"])

        self.admin_login()
        pay = self.client.post(f"/api/v1/tickets/{ticket_id}/pay")
        self.assertEqual(pay.status_code, 200)
        self.assertEqual(pay.get_json()["status"], "PAID")

        gate_after_payment = self.client.get("/api/v1/check_ticket?plate=LAG123AA")
        self.assertEqual(gate_after_payment.status_code, 200)
        self.assertEqual(gate_after_payment.get_json()["status"], "PASS")

    def test_non_speeding_vehicle_clears_without_ticket(self):
        entry = self.post_event("A", 2000, "ABC123XY")
        self.assertEqual(entry.status_code, 201)

        exit_event = self.post_event("B", 2020, "ABC123XY")
        self.assertEqual(exit_event.status_code, 200)
        self.assertEqual(exit_event.get_json()["status"], "CLEAR")

        tickets_redirect = self.client.get("/api/v1/tickets", follow_redirects=False)
        self.assertEqual(tickets_redirect.status_code, 302)
        self.assertIn("/admin/login", tickets_redirect.headers["Location"])

        self.admin_login()
        tickets = self.client.get("/api/v1/tickets")
        self.assertEqual(tickets.status_code, 200)
        self.assertEqual(tickets.get_json()["tickets"], [])

    def test_public_portal_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Check Your Traffic Ticket", response.data)

    def test_admin_dashboard_renders(self):
        redirect = self.client.get("/admin", follow_redirects=False)
        self.assertEqual(redirect.status_code, 302)
        self.assertIn("/admin/login", redirect.headers["Location"])

        self.admin_login()
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"UNILAG Admin Dashboard", response.data)

    def test_admin_login_page_renders(self):
        response = self.client.get("/admin/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Admin Login", response.data)

    def test_admin_api_requires_auth(self):
        response = self.client.get("/api/v1/tickets", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])

        self.admin_login()
        authed = self.client.get("/api/v1/tickets")
        self.assertEqual(authed.status_code, 200)

    def test_public_lookup_and_payment_flow(self):
        self.post_event("A", 3000, "KJA500AB")
        exit_event = self.post_event("B", 3005, "KJA500AB")

        lookup = self.client.get("/api/v1/public/tickets?plate=KJA500AB")
        self.assertEqual(lookup.status_code, 200)
        self.assertEqual(len(lookup.get_json()["tickets"]), 1)

    @patch("traffic_monitor.routes.paystack_verify_transaction")
    @patch("traffic_monitor.routes.paystack_initialize_transaction")
    def test_paystack_checkout_and_callback_marks_ticket_paid(self, mock_initialize, mock_verify):
        self.post_event("A", 4000, "AAA100BB")
        exit_event = self.post_event("B", 4005, "AAA100BB")
        ticket_id = exit_event.get_json()["ticket_id"]

        mock_initialize.return_value = {
            "status": True,
            "data": {
                "authorization_url": "https://checkout.paystack.com/test-ref",
                "access_code": "test-access",
                "reference": "UNILAG-TEST-REF",
            },
        }
        mock_verify.return_value = {
            "status": True,
            "data": {
                "status": "success",
                "reference": "UNILAG-TEST-REF",
                "gateway_response": "Successful",
                "paid_at": "2026-06-28T10:00:00Z",
                "metadata": {"ticket_id": ticket_id, "plate": "AAA100BB"},
            },
        }

        start = self.client.post(
            f"/portal/tickets/{ticket_id}/pay",
            data={"plate": "AAA100BB", "email": "user@example.com"},
            follow_redirects=False,
        )
        self.assertEqual(start.status_code, 302)
        self.assertEqual(start.headers["Location"], "https://checkout.paystack.com/test-ref")

        callback = self.client.get(
            "/portal/paystack/callback?reference=UNILAG-TEST-REF",
            follow_redirects=True,
        )
        self.assertEqual(callback.status_code, 200)
        self.assertIn(b"Payment confirmed", callback.data)

        gate_after_payment = self.client.get("/api/v1/check_ticket?plate=AAA100BB")
        self.assertEqual(gate_after_payment.status_code, 200)
        self.assertEqual(gate_after_payment.get_json()["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
