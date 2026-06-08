import frappe

def update_schemas():
    # Update A2C Lead
    lead_doc = frappe.get_doc("DocType", "A2C Lead")
    
    fields_to_add = [
        {"fieldname": "fayda_id", "fieldtype": "Data", "label": "Fayda ID", "insert_after": "phone_number"},
        {"fieldname": "consent_status", "fieldtype": "Select", "label": "Consent Status", "options": "\nPending\nApproved\nRejected", "insert_after": "status"},
        {"fieldname": "consent_request", "fieldtype": "Data", "label": "Consent Request", "insert_after": "consent_status"},
        {"fieldname": "consent_receipt", "fieldtype": "Data", "label": "Consent Receipt", "insert_after": "consent_request"},
        {"fieldname": "consent_data", "fieldtype": "Code", "options": "JSON", "label": "Consent Data", "read_only": 1, "insert_after": "consent_receipt"},
        {"fieldname": "loan_type", "fieldtype": "Data", "label": "Loan Type", "insert_after": "lead_source"},
        {"fieldname": "loan_amount", "fieldtype": "Currency", "options": "ETB", "label": "Loan Amount", "insert_after": "loan_type"},
        {"fieldname": "purpose_message", "fieldtype": "Data", "label": "Purpose Message", "insert_after": "loan_amount"},
    ]
    
    for field in fields_to_add:
        if not any(f.fieldname == field['fieldname'] for f in lead_doc.fields):
            lead_doc.append("fields", field)
            
    lead_doc.autoname = "format:LD-{#####}"
    lead_doc.save()
    print("A2C Lead schema updated successfully.")

    # Update Loan Application
    app_doc = frappe.get_doc("DocType", "Loan Application")
    
    if not any(f.fieldname == "lead_id" for f in app_doc.fields):
        app_doc.append("fields", {
            "fieldname": "lead_id", 
            "fieldtype": "Link", 
            "options": "A2C Lead", 
            "label": "Lead ID", 
            "insert_after": "application_id", 
            "in_list_view": 1
        })
        
    app_doc.autoname = "format:AGL-{#####}"
    app_doc.save()
    print("Loan Application schema updated successfully.")
    
update_schemas()
