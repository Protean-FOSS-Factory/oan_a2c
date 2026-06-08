import frappe
import json

@frappe.whitelist(allow_guest=True)
def receive_consent_data(**kwargs):
    """
    Webhook receiver for Odoo OpenG2P consent data.
    Bypasses custom JWT middleware.
    """
    try:
        # === Get Payload ===
        data = {}
        if frappe.request:
            data = frappe.request.get_json(silent=True) or {}
        if not data and kwargs:
            data = kwargs

        # Log the full payload to aid debugging ID mismatches
        frappe.logger().info(f"🔗 Webhook received. Keys: {list(data.keys())}")
        frappe.logger().info(f"🔗 Webhook raw payload: {json.dumps(data, default=str)[:2000]}")

        # === Extract consent_creation_request_id from multiple possible locations ===
        consent_request_id = None
        if isinstance(data.get("consent"), dict):
            consent_request_id = (
                data["consent"].get("consent_creation_request_id")
                or data["consent"].get("id")
                or data["consent"].get("name")
            )
        if not consent_request_id:
            consent_request_id = (
                data.get("consent_creation_request_id")
                or data.get("request_id")
                or data.get("id")
            )

        if not consent_request_id:
            frappe.logger().warning(f"🔗 Webhook: No consent ID found in payload. Keys: {list(data.keys())}")
            return {"status": "error", "message": "Missing consent_creation_request_id"}

        frappe.logger().info(f"🔗 Webhook: Looking up Consent Request with openg2p_consent_id = '{consent_request_id}'")

        # === Find Consent Request — try exact match first, then LIKE fallback ===
        consent_docs = frappe.get_all(
            "Consent Request",
            filters={"openg2p_consent_id": consent_request_id},
            fields=["name", "loan_application"],
            limit=1
        )

        # Fallback: OpenG2P sometimes sends a UUID that is a substring of what we stored
        if not consent_docs:
            frappe.logger().warning(f"🔗 Exact match not found. Trying partial match on '{consent_request_id}'.")
            consent_docs = frappe.db.sql(
                """
                SELECT name, loan_application
                FROM `tabConsent Request`
                WHERE openg2p_consent_id LIKE %s
                   OR %s LIKE CONCAT('%%', openg2p_consent_id, '%%')
                LIMIT 1
                """,
                (f"%{consent_request_id}%", consent_request_id),
                as_dict=True
            )

        if not consent_docs:
            frappe.logger().error(
                f"🔗 Webhook: No Consent Request matched ID '{consent_request_id}'. "
                f"Check openg2p_consent_id values in Consent Request doctype."
            )
            return {"status": "error", "message": f"Consent Request not found: {consent_request_id}"}

        loan_application_name = consent_docs[0].get("loan_application")
        consent_doc_name      = consent_docs[0].get("name")
        frappe.logger().info(f"🔗 Webhook: Found Consent Request '{consent_doc_name}', Loan Application '{loan_application_name}'")

        if not loan_application_name:
            # Still mark the consent doc as approved even if no loan app linked
            frappe.db.set_value("Consent Request", consent_doc_name, "status", "Approved")
            frappe.db.commit()
            return {"status": "success", "message": "Consent approved; no linked Loan Application"}

        # === Save Data to Loan Application ===
        loan_app = frappe.get_doc("Loan Application", loan_application_name)
        loan_app.consent_data   = json.dumps(data, indent=2, ensure_ascii=False)
        loan_app.consent_status = "Approved"
        loan_app.fayda_verified = 1
        loan_app.save(ignore_permissions=True)

        # Also mark Consent Request as Approved
        frappe.db.set_value("Consent Request", consent_doc_name, "status", "Approved")
        frappe.db.commit()

        frappe.logger().info(f"✅ Webhook SUCCESS: consent_data saved in Loan Application '{loan_app.name}'")
        return {
            "status": "success",
            "message": "Data stored successfully",
            "loan_application": loan_app.name,
            "consent_request": consent_doc_name,
        }

    except Exception as e:
        frappe.logger().error(f"Webhook Error: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}