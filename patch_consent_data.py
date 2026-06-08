"""
One-time script to backfill consent_data on Loan Applications that have
consent_status=Approved but empty consent_data (webhook never reached Frappe).

Run with:
  bench --site development.localhost execute patch_consent_data.run
OR load the actual webhook payload from OpenG2P for each application.
"""
import frappe, json

def run():
    # Find all approved apps missing consent_data
    apps = frappe.db.sql("""
        SELECT la.name, la.consent_request
        FROM `tabLoan Application` la
        WHERE la.consent_status = 'Approved'
          AND (la.consent_data IS NULL OR la.consent_data = '')
    """, as_dict=True)

    print(f"Found {len(apps)} applications missing consent_data")

    for app in apps:
        app_name = app["name"]
        cr_name  = app.get("consent_request")

        print(f"\nProcessing {app_name} (consent_request: {cr_name})")

        if not cr_name:
            # Try to find linked consent request
            linked = frappe.get_all(
                "Consent Request",
                filters={"loan_application": app_name},
                fields=["name", "openg2p_consent_id", "farmer_fayda_id"],
                order_by="creation desc",
                limit=1
            )
            if linked:
                cr_name = linked[0]["name"]
            else:
                print(f"  No linked Consent Request found. Skipping.")
                continue

        cr = frappe.db.get_value(
            "Consent Request", cr_name,
            ["openg2p_consent_id", "farmer_fayda_id"],
            as_dict=True
        )
        if not cr:
            print(f"  Consent Request {cr_name} not found. Skipping.")
            continue

        print(f"  openg2p_consent_id = {cr.openg2p_consent_id}")
        print(f"  farmer_fayda_id    = {cr.farmer_fayda_id}")

        # Build minimal consent_data from what we know
        # The farmer name will come from the res.partner fetch below
        from oan_a2c.consent.openg2p_client import OpenG2PConsentClient
        from frappe.utils import now_datetime

        try:
            client = OpenG2PConsentClient()
            farmer_db_id = client.get_farmer_by_fayda_id(cr.farmer_fayda_id)
            print(f"  farmer_db_id = {farmer_db_id}")

            farmer_record = {}
            selected_data = {}

            if farmer_db_id:
                records = client._admin_search_read(
                    "res.partner",
                    [["id", "=", farmer_db_id]],
                    ["id", "name", "email", "mobile", "phone"]
                )
                print(f"  res.partner result: {records}")
                if records:
                    f         = records[0]
                    full_name = (f.get("name") or "").strip()
                    parts     = full_name.split()
                    given     = parts[0].title() if parts else ""
                    family    = " ".join(p.title() for p in parts[1:]) if len(parts) > 1 else ""
                    mobile    = f.get("mobile") or f.get("phone") or ""

                    farmer_record = {"id": f.get("id"), "name": full_name}
                    selected_data = {
                        "farmer": {
                            "given_name":  given,
                            "family_name": family,
                            "email":       f.get("email") or "",
                            "phone_no":    [mobile] if mobile else [],
                        }
                    }
                    print(f"  Built: {given} {family} / {mobile}")

            payload = {
                "source": "frappe_backfill",
                "event_type": "WEBSUB_INDIVIDUAL_UPDATED",
                "published_at": str(now_datetime()),
                "consent": {
                    "consent_creation_request_id": cr.openg2p_consent_id,
                    "status": "approved",
                },
                "farmer": farmer_record,
                "selected_data": selected_data,
            }

            doc = frappe.get_doc("Loan Application", app_name)
            doc.consent_data   = json.dumps(payload, indent=2, ensure_ascii=False)
            doc.fayda_verified = 1
            doc.save(ignore_permissions=True)
            frappe.db.commit()
            print(f"  ✅ consent_data saved for {app_name}")

        except Exception as e:
            print(f"  ❌ Failed: {e}")
            import traceback; traceback.print_exc()
