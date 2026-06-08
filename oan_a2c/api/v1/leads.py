import frappe
from frappe import _



@frappe.whitelist(allow_guest=False)
def get_leads(
	start=0,
	page_length=20,
	search_query=None,
	status=None,
	lead_source=None,
	start_date=None,
	end_date=None
):
	"""
	Retrieves a paginated list of A2C Leads with multi-faceted search and filter configurations.

	Security Specs:
	  - Enforces JWT session validation via whitelist allow_guest=False.
	  - Explicitly executes frappe.has_permission("A2C Lead", "read", throw=True).
	  - Leverages frappe.get_list() to ensure Frappe's RBAC and User Permissions (multi-tenant
	    data isolation) are dynamically applied at the database query layer.
	  - Parametrizes all inputs to prevent SQL Injection.
	"""
	# 1. Enforce Role-Based Access Control
	frappe.has_permission("A2C Lead", "read", throw=True)

	# 2. Sanitize and bound pagination inputs to prevent memory exhaustion DoS
	try:
		start = int(start or 0)
		if start < 0:
			start = 0
	except ValueError:
		start = 0

	try:
		page_length = int(page_length or 20)
		if page_length < 1:
			page_length = 20
		elif page_length > 100:
			page_length = 100  # Strict upper bound limit
	except ValueError:
		page_length = 20

	# 3. Construct Filters
	filters = []

	# Apply Status Filter
	if status:
		# Sanitize input against valid choices
		allowed_statuses = ("Open", "Initiated", "Qualified", "Not Interested", "Processed")
		if status in allowed_statuses:
			filters.append(["status", "=", status])

	# Apply Lead Source Filter
	if lead_source:
		allowed_sources = ("Missed Call", "IVR", "SMS", "Agent Entry")
		if lead_source in allowed_sources:
			filters.append(["lead_source", "=", lead_source])

	# Apply Creation Date Range Filter
	if start_date and end_date:
		filters.append(["creation", "between", [start_date, end_date]])
	elif start_date:
		filters.append(["creation", ">=", start_date])
	elif end_date:
		filters.append(["creation", "<=", end_date])

	# 4. Construct Search Or-Filters
	or_filters = []
	if search_query:
		# Search by Lead ID (name), Phone Number, or External ID
		search_query_param = f"%{search_query}%"
		or_filters.append(["name", "like", search_query_param])
		or_filters.append(["phone_number", "like", search_query_param])
		or_filters.append(["external_id", "like", search_query_param])

	# 5. Fetch Total Record Count (Respecting RBAC and User Permissions via get_list counted select)
	count_res = frappe.get_list(
		"A2C Lead",
		filters=filters,
		or_filters=or_filters or None,
		fields=[{"COUNT": "*"}]
	)
	total_count = count_res[0].get("COUNT(*)") if count_res else 0

	# 6. Fetch Paginated Records
	leads = frappe.get_list(
		"A2C Lead",
		fields=["name", "phone_number", "external_id", "lead_source", "status", "assigned_to", "creation"],
		filters=filters,
		or_filters=or_filters or None,
		limit_start=start,
		page_length=page_length,
		order_by="creation desc"
	)

	return {
		"status": "success",
		"start": start,
		"page_length": page_length,
		"total_count": total_count,
		"results": leads
	}




@frappe.whitelist(allow_guest=False)
def get_lead_summary():
	"""
	Returns aggregated lead counts: total count and status-wise counts.
	Enforces JWT session validation and native role-based permissions (RBAC).
	"""
	# 1. Enforce Role-Based Access Control
	frappe.has_permission("A2C Lead", "read", throw=True)

	allowed_statuses = ("Open", "Initiated", "Qualified", "Not Interested", "Processed")
	counts_by_status = {}
	total_count = 0

	for status in allowed_statuses:
		cnt_res = frappe.get_list(
			"A2C Lead",
			filters={"status": status},
			fields=[{"COUNT": "*"}]
		)
		count = cnt_res[0].get("COUNT(*)") if cnt_res else 0
		counts_by_status[status] = count
		total_count += count

	return {
		"status": "success",
		"total": total_count,
		"by_status": counts_by_status
	}


@frappe.whitelist(allow_guest=False)
def search_farmer(**kwargs):
	"""
	Step 1 of the new A2C flow: Search for a farmer in OpenG2P by Fayda ID.

	Returns a farmer profile preview so the UI can confirm the correct farmer
	before proceeding to OTP. No Frappe document is created at this stage.

	Required params: fayda_id
	"""
	data = {}
	try:
		if frappe.request:
			data = frappe.request.get_json(silent=True) or {}
	except Exception:
		pass

	form = getattr(frappe, "form_dict", {})

	def _get(key, default=None):
		return kwargs.get(key) or data.get(key) or form.get(key) or default

	fayda_id = _get("fayda_id")
	if not fayda_id:
		frappe.throw(_("fayda_id is required"), frappe.MandatoryError)

	try:
		from oan_a2c.consent.openg2p_client import OpenG2PConsentClient
		client = OpenG2PConsentClient()
	except Exception as e:
		frappe.throw(_("Could not connect to OpenG2P: {0}").format(str(e)))

	# Look up farmer by Fayda ID
	farmer_db_id = client.get_farmer_by_fayda_id(fayda_id)
	if not farmer_db_id:
		return {
			"status": "not_found",
			"found": False,
			"fayda_id": fayda_id,
			"message": "No farmer found with the given Fayda ID in OpenG2P."
		}

	# Fetch basic profile fields from res.partner
	farmer_records = client._admin_search_read(
		"res.partner",
		[["id", "=", farmer_db_id]],
		["id", "name", "email", "mobile", "phone"]
	)

	farmer_profile = {}
	if farmer_records:
		f = farmer_records[0]
		full_name = (f.get("name") or "").strip()
		parts = full_name.split()
		farmer_profile = {
			"farmer_db_id": farmer_db_id,
			"fayda_id": fayda_id,
			"full_name": full_name,
			"given_name": parts[0].title() if parts else "",
			"family_name": " ".join(p.title() for p in parts[1:]) if len(parts) > 1 else "",
			"email": f.get("email") or "",
			"mobile": f.get("mobile") or f.get("phone") or "",
		}
	else:
		farmer_profile = {
			"farmer_db_id": farmer_db_id,
			"fayda_id": fayda_id,
			"full_name": "",
			"given_name": "",
			"family_name": "",
			"email": "",
			"mobile": "",
		}

	return {
		"status": "success",
		"found": True,
		"farmer": farmer_profile,
		"message": "Farmer found. Proceed to request OTP."
	}

@frappe.whitelist(allow_guest=False)
def schedule_visit(lead_id, visit_date, notes=None):
	"""
	2b. Schedule Visit API for Lead
	"""
	frappe.has_permission("A2C Lead", "write", throw=True)
	if not lead_id or not visit_date:
		frappe.throw(_("lead_id and visit_date are required"), frappe.MandatoryError)
		
	lead = frappe.get_doc("A2C Lead", lead_id)
	lead.visit_date = visit_date
	if notes:
		lead.call_notes = (lead.call_notes or "") + f"\nVisit Notes: {notes}"
	lead.save()
	
	return {"status": "success", "message": "Visit scheduled successfully"}

@frappe.whitelist(allow_guest=False)
def send_notification(lead_id, message):
	"""
	2f. Notification API for Lead
	Sends an SMS or internal notification.
	"""
	frappe.has_permission("A2C Lead", "read", throw=True)
	if not lead_id or not message:
		frappe.throw(_("lead_id and message are required"), frappe.MandatoryError)
		
	# Placeholder for actual SMS/Email integration
	frappe.msgprint(f"Notification Sent to Lead {lead_id}: {message}")
	
	return {"status": "success", "message": "Notification sent successfully"}

@frappe.whitelist(allow_guest=False)
def submit_lead(lead_id, **kwargs):
	"""
	2g. Submit Lead API
	Saves all credit/farm information to the lead and marks it as Initiated.
	"""
	frappe.has_permission("A2C Lead", "write", throw=True)
	if not lead_id:
		frappe.throw(_("lead_id is required"), frappe.MandatoryError)
		
	data = frappe.request.get_json(silent=True) or kwargs
	
	lead = frappe.get_doc("A2C Lead", lead_id)
	
	# Update fields from JSON
	updatable_fields = ["loan_type", "loan_amount", "purpose_message", "region", "zone", "woreda", "agent_id"]
	for f in updatable_fields:
		if f in data:
			setattr(lead, f, data[f])
			
	lead.status = "Initiated"
	lead.save()
	
	return {"status": "success", "message": "Lead submitted successfully"}

@frappe.whitelist(allow_guest=False)
def verify_lead(lead_id):
	"""
	3a. Verify Lead API
	Transitions the lead to Qualified.
	"""
	frappe.has_permission("A2C Lead", "write", throw=True)
	if not lead_id:
		frappe.throw(_("lead_id is required"), frappe.MandatoryError)
		
	lead = frappe.get_doc("A2C Lead", lead_id)
	lead.status = "Qualified"
	lead.save()
	
	return {"status": "success", "message": "Lead verified successfully"}

@frappe.whitelist(allow_guest=False)
def reject_lead(lead_id, reason=None):
	"""
	3b. Reject Lead API
	Transitions the lead to Rejected or Not Interested.
	"""
	frappe.has_permission("A2C Lead", "write", throw=True)
	if not lead_id:
		frappe.throw(_("lead_id is required"), frappe.MandatoryError)
		
	lead = frappe.get_doc("A2C Lead", lead_id)
	lead.status = "Not Interested"
	if reason:
		lead.call_notes = (lead.call_notes or "") + f"\nRejection Reason: {reason}"
	lead.save()
	
	return {"status": "success", "message": "Lead rejected successfully"}



@frappe.whitelist(allow_guest=False)
def create_lead(phone_number=None, first_name=None, last_name=None, email=None, location=None, lead_source="Agent Entry", status="Open", external_id=None):
    frappe.has_permission("A2C Lead", "create", throw=True)

    if not phone_number:
        frappe.throw(frappe._("phone_number is required"), frappe.MandatoryError)

    lead = frappe.new_doc("A2C Lead")
    lead.phone_number = phone_number
    lead.first_name = first_name
    lead.last_name = last_name
    lead.email = email
    lead.location = location
    lead.lead_source = lead_source
    lead.status = status or "Open"
    if external_id:
        lead.external_id = external_id
        
    lead.insert(ignore_permissions=False)
    frappe.db.commit()

    return {
        "status": "success",
        "data": {
            "name": lead.name
        },
        "lead_id": lead.name,
        "message": frappe._("Lead created successfully.")
    }
