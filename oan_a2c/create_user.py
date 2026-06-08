import frappe

def create():
    if not frappe.db.exists("Role", "Development Agent"):
        frappe.get_doc({"doctype": "Role", "role_name": "Development Agent"}).insert(ignore_permissions=True)

    if not frappe.db.exists("User", "agent@oan.com"):
        user = frappe.get_doc({
            "doctype": "User",
            "email": "agent@oan.com",
            "first_name": "Agent",
            "last_name": "Test",
            "send_welcome_email": 0
        })
        user.insert(ignore_permissions=True)
        user.add_roles("Development Agent")
    else:
        user = frappe.get_doc("User", "agent@oan.com")
        user.add_roles("Development Agent")

    from frappe.core.doctype.user.user import update_password
    update_password(new_password="password123", user="agent@oan.com")
    frappe.db.commit()
    print("User created successfully")
