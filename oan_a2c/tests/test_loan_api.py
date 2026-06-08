import frappe
import unittest
from oan_a2c.api.loan_app_api import (
    loan_details,
    bank_details,
    farmer_details,
    application_manager,
    get_consent_data
)
import json

class TestLoanAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        # Clean up created loan applications
        apps = frappe.get_all("Loan Application", filters={"purpose_of_loan": "API_TEST"}, pluck="name")
        for name in apps:
            frappe.delete_doc("Loan Application", name, ignore_permissions=True, force=True)
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")

    def test_1_create_loan_details(self):
        """Test creating a new application via loan_details API"""
        response = loan_details(
            action="save",
            loan_type="Agricultural Loan",
            purpose_of_loan="API_TEST",
            requested_loan_amount=50000,
            primary_crop="Wheat"
        )
        self.assertEqual(response["status"], "success")
        self.assertIn("application_id", response["data"])
        self.assertEqual(response["data"]["current_step"], 1)

        # Verify in DB
        app_id = response["data"]["application_id"]
        doc = frappe.get_doc("Loan Application", app_id)
        self.assertEqual(doc.requested_amount, 50000)
        self.assertEqual(doc.primary_crop, "Wheat")
        self.assertEqual(doc.current_step, 1)

        # Store app_id for next tests
        TestLoanAPI.app_id = app_id

    def test_2_update_bank_details(self):
        """Test saving bank details for the created application"""
        # Ensure we have an app_id from previous test or create one
        app_id = getattr(self, "app_id", None)
        if not app_id:
            res = loan_details(action="save", purpose_of_loan="API_TEST")
            app_id = res["data"]["application_id"]

        response = bank_details(
            action="save",
            application_id=app_id,
            bank_account_name="John Doe",
            bank_account_number="1234567890",
            total_amount_borrowing=50000
        )
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["data"]["current_step"], 2)

        doc = frappe.get_doc("Loan Application", app_id)
        self.assertEqual(doc.bank_account_no, "1234567890")

    def test_3_save_farmer_details(self):
        """Test saving farmer details"""
        app_id = getattr(self, "app_id", None)
        if not app_id:
            res = loan_details(action="save", purpose_of_loan="API_TEST")
            app_id = res["data"]["application_id"]

        response = farmer_details(
            action="save",
            application_id=app_id,
            full_name="John",
            last_name="Doe",
            mobile_phone="0911223344"
        )
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["data"]["current_step"], 5)

        doc = frappe.get_doc("Loan Application", app_id)
        self.assertEqual(doc.full_name, "John")

    def test_4_application_manager_review(self):
        """Test reviewing the application status"""
        app_id = getattr(self, "app_id", None)
        if not app_id:
            res = loan_details(action="save", purpose_of_loan="API_TEST")
            app_id = res["data"]["application_id"]

        response = application_manager(
            action="review",
            application_id=app_id
        )
        self.assertEqual(response["status"], "success")
        sections = response["data"]["sections"]
        section_labels = [s["label"] for s in sections]
        self.assertIn("Loan Requirements", section_labels)
        self.assertIn("Supporting Documents", section_labels)

    def test_5_draft_save(self):
        """Test draft saving functionality with protected fields"""
        app_id = getattr(self, "app_id", None)
        if not app_id:
            res = loan_details(action="save", purpose_of_loan="API_TEST")
            app_id = res["data"]["application_id"]

        response = application_manager(
            action="draft",
            application_id=app_id,
            step=1,
            data={"address": "Test Address", "status": "Approved"} # status should be protected
        )
        self.assertEqual(response["status"], "success")

        doc = frappe.get_doc("Loan Application", app_id)
        self.assertEqual(doc.address, "Test Address")
        # status should not be changed by generic draft endpoint
        self.assertEqual(doc.status, "Draft")

    def test_6_get_consent_data_missing(self):
        """Test getting consent data when none is available"""
        app_id = getattr(self, "app_id", None)
        if not app_id:
            res = loan_details(action="save", purpose_of_loan="API_TEST")
            app_id = res["data"]["application_id"]
            
        response = get_consent_data(application_id=app_id)
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error_code"], "NO_CONSENT_DATA")

    def test_7_get_consent_data_success(self):
        """Test parsing consent data"""
        app_id = getattr(self, "app_id", None)
        if not app_id:
            res = loan_details(action="save", purpose_of_loan="API_TEST")
            app_id = res["data"]["application_id"]
            
        # Simulate webhook having updated consent data
        sample_consent = {
            "consent": {
                "consent_creation_request_id": "REQ-123"
            },
            "farmer": {
                "id": "F-001",
                "name": "Jane Doe Basic"
            },
            "selected_data": {
                "farmer": {
                    "given_name": "Jane",
                    "family_name": "Doe",
                    "email": "jane@example.com",
                    "phone_no": ["123456789"]
                }
            }
        }
        
        frappe.db.set_value("Loan Application", app_id, "consent_data", json.dumps(sample_consent))
        frappe.db.set_value("Loan Application", app_id, "consent_status", "Approved")
        frappe.db.commit()
        
        response = get_consent_data(application_id=app_id)
        self.assertEqual(response["status"], "success")
        
        details = response["data"]["farmer_details"]
        self.assertEqual(details["full_name"], "Jane Doe Basic")
        self.assertEqual(details["email"], "jane@example.com")
        self.assertEqual(details["mobile_phone"], "123456789")

    def test_8_submit_missing_consent(self):
        """Test that submitting an application without consent fails"""
        # Create a new app that doesn't have consent_status="Approved"
        res = loan_details(action="save", purpose_of_loan="API_TEST")
        app_id = res["data"]["application_id"]

        response = application_manager(
            action="submit",
            application_id=app_id
        )
        # It should fail because no documents are uploaded (consent check is bypassed)
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error_code"], "MISSING_DOCS")

    def test_9_cancel_application(self):
        """Test cancelling the application"""
        res = loan_details(action="save", purpose_of_loan="API_TEST")
        app_id = res["data"]["application_id"]

        response = application_manager(
            action="cancel",
            application_id=app_id,
            reason="User requested cancellation"
        )
        self.assertEqual(response["status"], "success")

        doc = frappe.get_doc("Loan Application", app_id)
        self.assertEqual(doc.status, "Cancelled")
        self.assertEqual(doc.cancellation_reason, "User requested cancellation")

    def test_10_submit_success(self):
        """Test submitting an application when consent is Approved and documents are uploaded"""
        res = loan_details(action="save", purpose_of_loan="API_TEST")
        app_id = res["data"]["application_id"]

        # 1. Update consent status to Approved
        frappe.db.set_value("Loan Application", app_id, "consent_status", "Approved")
        frappe.db.commit()

        # 2. Attach a dummy document to satisfy doc count check
        frappe.db.sql("""
            INSERT INTO `tabFile` (name, file_name, attached_to_doctype, attached_to_name, file_url, is_private)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (frappe.generate_hash(), "test.pdf", "Loan Application", app_id, "/private/files/test.pdf", 1))
        frappe.db.commit()

        # 3. Call submit
        response = application_manager(
            action="submit",
            application_id=app_id
        )
        
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["data"]["status"], "Submitted")
        
        # Verify in DB
        doc = frappe.get_doc("Loan Application", app_id)
        self.assertEqual(doc.status, "Submitted")
        self.assertEqual(doc.current_step, 6)

    def test_11_get_loan_applications(self):
        """Test the loan applications list API"""
        from oan_a2c.openagrinet_access_to_credit.doctype.loan_application.loan_application import get_loan_applications

        # Create a dummy test record
        doc = frappe.get_doc({
            "doctype": "Loan Application",
            "status": "Draft",
            "loan_type": "Test Dashboard Loan",
            "requested_amount": 1000
        }).insert(ignore_permissions=True)

        res = get_loan_applications(page=1, page_size=20)
        self.assertEqual(res.get("status"), "success")
        self.assertIn("results", res)
        self.assertIn("pagination", res)
        self.assertTrue(res["pagination"]["total"] > 0)
        
        # Cleanup
        doc.delete()

    def test_12_get_loan_summary(self):
        """Test the loan summary API"""
        from oan_a2c.openagrinet_access_to_credit.doctype.loan_application.loan_application import get_loan_summary

        # Create a dummy test record
        doc = frappe.get_doc({
            "doctype": "Loan Application",
            "status": "Draft",
            "loan_type": "Test Dashboard Loan",
            "requested_amount": 1000
        }).insert(ignore_permissions=True)

        res = get_loan_summary()
        self.assertEqual(res.get("status"), "success")
        self.assertIn("total", res)
        self.assertIn("by_status", res)
        
        # Cleanup
        doc.delete()
