# pyright: reportMissingImports=false
import frappe
from frappe.utils import now_datetime
import json


# ─── Helpers ────────────────────────────────────────────────────────────────

def success(data):
    return {"status": "success", "data": data}

def error(code, message):
    return {"status": "error", "error_code": code, "message": message}

def _get_app(application_id, editable=True):
    if not application_id:
        return None, error("MISSING_APP_ID", "application_id is required.")
    if not frappe.db.exists("Loan Application", application_id):
        return None, error("NOT_FOUND", f"Application {application_id} not found.")
    doc = frappe.get_doc("Loan Application", application_id)
    if editable and doc.status not in ["Draft", "In Progress"]:
        return None, error("NOT_EDITABLE", "This application is already submitted.")
    return doc, None

def _parse_body(kwargs):
    if not kwargs or list(kwargs.keys()) == ["cmd"]:
        # 1. Fallback for form-data (e.g. file uploads)
        try:
            if hasattr(frappe.local, "request") and hasattr(frappe.local.request, "form") and frappe.local.request.form:
                for k, v in frappe.local.request.form.items():
                    kwargs[k] = v
        except Exception:
            pass

        # 2. Fallback for JSON body (when Content-Type header is missing/altered)
        if len(kwargs) <= 1:
            try:
                raw_data = frappe.local.request.get_data()
                if raw_data:
                    body_params = json.loads(raw_data.decode("utf-8"))
                    if isinstance(body_params, dict):
                        kwargs.update(body_params)
            except Exception:
                pass
    return kwargs


@frappe.whitelist(allow_guest=False)
def create_loan_from_lead(**kwargs):
    """
    NEW FLOW — Step 4: Create a Loan Application from an approved A2C Lead.
    
    Required params: lead_id
    Returns: { application_id, status: 'success' }
    """
    kwargs = _parse_body(kwargs)
    lead_id = kwargs.get("lead_id")
    
    if not lead_id:
        return error("MISSING_LEAD_ID", "lead_id is required.")
        
    if not frappe.db.exists("A2C Lead", lead_id):
        return error("NOT_FOUND", f"A2C Lead {lead_id} not found.")
        
    lead_doc = frappe.get_doc("A2C Lead", lead_id)
    
    if lead_doc.consent_status != "Approved":
        return error("CONSENT_NOT_APPROVED", f"Lead {lead_id} does not have an approved consent.")
        
    try:
        # Create Loan Application
        loan_app_doc = frappe.get_doc({
            "doctype": "Loan Application",
            "status": "Draft",
            "current_step": 1,
            "loan_officer": frappe.session.user,
            "lead_id": lead_id,
            "farmer_fayda_id": lead_doc.fayda_id,
            "consent_status": lead_doc.consent_status,
            "consent_request": lead_doc.consent_request,
            "consent_receipt": lead_doc.consent_receipt,
            "consent_data": lead_doc.consent_data,
            "fayda_verified": 1 if lead_doc.consent_status == "Approved" else 0,
            
            # Copy Credit Information
            "loan_type": lead_doc.loan_type,
            "requested_amount": lead_doc.loan_amount,
            "purpose_of_loan": lead_doc.purpose_message,
        })
        
        # Populate basic name and phone from Lead if available
        if lead_doc.first_name:
            loan_app_doc.full_name = lead_doc.first_name
        if lead_doc.last_name:
            loan_app_doc.last_name = lead_doc.last_name
        if lead_doc.phone_number:
            loan_app_doc.mobile_phone = lead_doc.phone_number
            
        loan_app_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return success({"application_id": loan_app_doc.name, "message": "Loan Application created successfully from Lead."})
        
    except Exception as e:
        return error("CREATION_FAILED", str(e))



# ─── API 1: Loan Details ─────────────────────────────────────────────────────

_LOAN_DETAIL_FIELDS = [
    "loan_type", "purpose_of_loan", "requested_amount", "loan_duration_months",
    "nearest_branch", "primary_crop", "crop_variety", "address",
    "quantity_requested_kg", "unit_price", "total_seed_cost", "land_size_ha",
    "expected_yield", "expected_harvest_date", "fertilizer_used",
    "other_farming_activities", "farmer_group", "animal_reared", "farm_equipment",
    "farm_size_hectares", "region", "zone", "woreda", "kebele",
    "harvest_aggregator_type", "name_of_cooperative",
    "dap_quantity_kg", "urea_quantity_kg", "unit_price_per_fertilizer_type", "total_fertilizer_cost",
    "type_of_agrochemical", "agrochemical_quantity_requested", "agrochemical_unit_price", "total_crop_protection_cost",
    "selected_input_supplier",
    "upfront_contribution_male_percent", "upfront_contribution_female_percent", "crop_insurance_premium_percent",
]

@frappe.whitelist(allow_guest=False)
def loan_details(**kwargs):
    kwargs = _parse_body(kwargs)
    action = kwargs.get("action", "save")

    if action == "get":
        application_id = kwargs.get("application_id")
        doc, err = _get_app(application_id, editable=False)
        if err:
            return err
        data = {f: getattr(doc, f, None) for f in _LOAN_DETAIL_FIELDS}
        data["application_id"] = doc.name
        data["current_step"] = doc.current_step
        data["status"] = doc.status
        return success(data)

    if action == "save":
        application_id = kwargs.get("application_id")
        fields = {
            "loan_type":                              kwargs.get("loan_type"),
            "purpose_of_loan":                        kwargs.get("purpose_of_loan"),
            "requested_amount":                        kwargs.get("requested_loan_amount"),
            "loan_duration_months":                   kwargs.get("loan_duration_months"),
            "nearest_branch":                         kwargs.get("nearest_branch"),
            "primary_crop":                           kwargs.get("primary_crop"),
            "crop_variety":                           kwargs.get("crop_variety"),
            "address":                                kwargs.get("address"),
            "quantity_requested_kg":                  kwargs.get("quantity_requested_kg"),
            "unit_price":                             kwargs.get("unit_price"),
            "total_seed_cost":                        kwargs.get("total_seed_cost"),
            "land_size_ha":                           kwargs.get("land_size_hectares"),
            "expected_yield":                         kwargs.get("expected_yield"),
            "expected_harvest_date":                  kwargs.get("expected_harvest_date"),
            "fertilizer_used":                        kwargs.get("fertilizer_used"),
            "other_farming_activities":               kwargs.get("other_farming_activities"),
            "farmer_group":                           kwargs.get("farmer_group"),
            "animal_reared":                          kwargs.get("animal_reared"),
            "farm_equipment":                         kwargs.get("farm_equipment"),
            "farm_size_hectares":                     kwargs.get("farm_size_hectares"),
            "region":                                 kwargs.get("region"),
            "zone":                                   kwargs.get("zone"),
            "woreda":                                 kwargs.get("woreda"),
            "kebele":                                 kwargs.get("kebele"),
            "harvest_aggregator_type":                kwargs.get("harvest_aggregator_type"),
            "name_of_cooperative":                    kwargs.get("name_of_cooperative"),
            "dap_quantity_kg":                        kwargs.get("dap_quantity_kg"),
            "urea_quantity_kg":                       kwargs.get("urea_quantity_kg"),
            "unit_price_per_fertilizer_type":         kwargs.get("unit_price_per_fertilizer_type"),
            "total_fertilizer_cost":                  kwargs.get("total_fertilizer_cost"),
            # Crop Protection — fixed field names to match doctype
            "type_of_agrochemical":                   kwargs.get("type_of_agrochemical"),
            "agrochemical_quantity_requested":         kwargs.get("agrochemical_quantity_requested"),
            "agrochemical_unit_price":                kwargs.get("agrochemical_unit_price"),
            "total_crop_protection_cost":             kwargs.get("total_crop_protection_cost"),
            # Financing & Pricing
            "selected_input_supplier":                kwargs.get("selected_input_supplier"),
            "upfront_contribution_male_percent":      kwargs.get("upfront_contribution_male_percent"),
            "upfront_contribution_female_percent":    kwargs.get("upfront_contribution_female_percent"),
            "crop_insurance_premium_percent":         kwargs.get("crop_insurance_premium_percent"),
        }

        try:
            if not application_id:
                doc = frappe.get_doc({
                    "doctype": "Loan Application",
                    "status": "Draft",
                    "current_step": 1,
                    "loan_officer": frappe.session.user,
                    **{k: v for k, v in fields.items() if v is not None},
                })
                doc.insert(ignore_permissions=True)
            else:
                doc, err = _get_app(application_id)
                if err:
                    return err
                for k, v in fields.items():
                    if v is not None and hasattr(doc, k):
                        setattr(doc, k, v)
                doc.current_step = max(int(getattr(doc, "current_step", 0)), 1)
                doc.save(ignore_permissions=True)

            saved = {f: getattr(doc, f, None) for f in _LOAN_DETAIL_FIELDS}
            saved["application_id"] = doc.name
            saved["current_step"] = 1
            return success(saved)
        except Exception as e:
            return error("SAVE_FAILED", str(e))

    return error("INVALID_ACTION", f"Unknown action: {action}")


# ─── API 2: Bank Details ─────────────────────────────────────────────────────

_BANK_FIELDS = [
    "bank_account_name", "bank_account_no", "bank_name", "bank_swift_ifsc_code",
    "mobile_account_name", "mobile_payments_number", "total_amount_borrowing", "tax_id",
]

@frappe.whitelist(allow_guest=False)
def bank_details(**kwargs):
    kwargs = _parse_body(kwargs)
    action = kwargs.get("action", "save")

    if action == "get":
        application_id = kwargs.get("application_id")
        doc, err = _get_app(application_id, editable=False)
        if err:
            return err
        data = {f: getattr(doc, f, None) for f in _BANK_FIELDS}
        data["application_id"] = doc.name
        data["current_step"] = doc.current_step
        return success(data)

    if action == "save":
        application_id = kwargs.get("application_id")
        doc, err = _get_app(application_id)
        if err:
            return err

        total_amount = kwargs.get("total_amount_borrowing")
        tax_id = kwargs.get("tax_id")
        try:
            total_amount_float = float(total_amount) if total_amount else 0
        except Exception:
            total_amount_float = 0

        if total_amount_float > 100000 and not tax_id:
            return error("TAX_ID_REQUIRED", "Tax ID is required for loan amounts above ETB 100,000.")

        fields = {
            "bank_account_name":      kwargs.get("bank_account_name"),
            "bank_account_no":        kwargs.get("bank_account_number"),
            "bank_name":              kwargs.get("bank_name"),
            "bank_swift_ifsc_code":   kwargs.get("bank_swift_ifsc_code"),
            "mobile_account_name":    kwargs.get("mobile_account_name"),
            "mobile_payments_number": kwargs.get("mobile_payments_number"),
            "total_amount_borrowing": total_amount,
            "tax_id":                 tax_id,
        }
        try:
            for k, v in fields.items():
                if v is not None and hasattr(doc, k):
                    setattr(doc, k, v)
            doc.current_step = max(getattr(doc, "current_step", 1), 2)
            doc.save(ignore_permissions=True)
            saved = {f: getattr(doc, f, None) for f in _BANK_FIELDS}
            saved["application_id"] = doc.name
            saved["current_step"] = 2
            return success(saved)
        except Exception as e:
            return error("SAVE_FAILED", str(e))

    return error("INVALID_ACTION", f"Unknown action: {action}")


# ─── API 3: Supporting Documents ─────────────────────────────────────────────

_ALLOWED_DOC_TYPES = [
    "Marriage Certificate",
    "Identity Document",
    "Land Ownership Proof",
    "Certification Photo",
    "Additional Document",
]

@frappe.whitelist(allow_guest=False)
def supporting_documents(**kwargs):
    kwargs = _parse_body(kwargs)
    action = kwargs.get("action", "list")

    if action == "upload":
        application_id = kwargs.get("application_id")
        doc, err = _get_app(application_id)
        if err:
            return err

        document_type = kwargs.get("document_type")
        marriage_status = kwargs.get("marriage_status")
        acknowledge_discrepancy = kwargs.get("acknowledge_discrepancy", False)

        if document_type not in _ALLOWED_DOC_TYPES:
            return error("INVALID_DOC_TYPE", f"document_type must be one of: {_ALLOWED_DOC_TYPES}")

        uploaded_file = frappe.request.files.get("file")
        if not uploaded_file:
            return error("NO_FILE", "No file was uploaded.")

        try:
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": uploaded_file.filename,
                "attached_to_doctype": "Loan Application",
                "attached_to_name": application_id,
                "attached_to_field": document_type.lower().replace(" ", "_"),
                "is_private": 1,
                "content": uploaded_file.read(),
            })
            file_doc.save(ignore_permissions=True)

            if marriage_status and hasattr(doc, "marriage_status"):
                doc.marriage_status = marriage_status
            if acknowledge_discrepancy:
                doc.acknowledge_discrepancy = 1
            doc.current_step = max(getattr(doc, "current_step", 1), 3)
            doc.save(ignore_permissions=True)

            return success({
                "document_id": file_doc.name,
                "document_type": document_type,
                "file_name": file_doc.file_name,
                "file_url": file_doc.file_url,
                "upload_status": "uploaded",
                "current_step": 3,
            })
        except Exception as e:
            return error("UPLOAD_FAILED", str(e))

    if action == "list":
        application_id = kwargs.get("application_id")
        if not application_id:
            return error("MISSING_APP_ID", "application_id is required.")

        doc, err = _get_app(application_id, editable=False)
        if err:
            return err

        files = frappe.get_all(
            "File",
            filters={"attached_to_doctype": "Loan Application", "attached_to_name": application_id},
            fields=["name", "file_name", "file_url", "attached_to_field", "creation"],
        )

        # Group documents by type for the UI cards
        grouped = {t: [] for t in _ALLOWED_DOC_TYPES}
        for f in files:
            key = (f.get("attached_to_field") or "").replace("_", " ").title()
            bucket = key if key in grouped else "Additional Document"
            grouped[bucket].append({
                "document_id": f["name"],
                "file_name": f["file_name"],
                "file_url": f["file_url"],
                "creation": f["creation"],
            })

        return success({
            "marriage_status": getattr(doc, "marriage_status", None),
            "acknowledge_discrepancy": bool(getattr(doc, "acknowledge_discrepancy", False)),
            "documents": files,
            "documents_by_type": grouped,
            "current_step": doc.current_step,
        })

    if action == "delete":
        application_id = kwargs.get("application_id")
        document_id = kwargs.get("document_id")
        if not document_id:
            return error("MISSING_DOC_ID", "document_id is required.")
        if not application_id:
            return error("MISSING_APP_ID", "application_id is required.")
        file_owner = frappe.db.get_value("File", document_id, ["attached_to_doctype", "attached_to_name"], as_dict=True)
        if not file_owner or file_owner.attached_to_doctype != "Loan Application" or file_owner.attached_to_name != application_id:
            return error("NOT_AUTHORIZED", "This file does not belong to the specified application.")
        try:
            frappe.delete_doc("File", document_id, ignore_permissions=True)
            return success({"deleted": document_id})
        except Exception as e:
            return error("DELETE_FAILED", str(e))

    return error("INVALID_ACTION", f"Unknown action: {action}")


# ─── API 5: Farmer Details ────────────────────────────────────────────────────

_FARMER_FIELDS = [
    "full_name", "last_name", "mobile_phone", "date_of_birth", "gender",
    "woreda", "kebele", "id_type", "id_number", "language",
    "land_size_acres", "farm_id", "farm_polygon", "land_acreage", "farm_land_number",
    "marital_status", "size_of_family", "number_of_children",
    "no_of_females_family", "no_of_males_family", "family_member_owns_land",
    "source_of_income", "education_level",
    "total_farmland_as_landowner", "total_farmland_as_crop_sharing", "total_farmland_as_rented",
    "certification_id",
    "farmland_size_hectares", "land_ownership_status", "soil_fertility_minerals", "moisture_levels",
]

@frappe.whitelist(allow_guest=False)
def farmer_details(**kwargs):
    kwargs = _parse_body(kwargs)
    action = kwargs.get("action", "save")

    if action == "get":
        application_id = kwargs.get("application_id")
        doc, err = _get_app(application_id, editable=False)
        if err:
            return err
        data = {f: getattr(doc, f, None) for f in _FARMER_FIELDS}
        data["application_id"] = doc.name
        data["current_step"] = doc.current_step
        return success(data)

    if action == "save":
        application_id = kwargs.get("application_id")
        doc, err = _get_app(application_id)
        if err:
            return err

        field_map = {
            # Basic Information
            "full_name":                    kwargs.get("full_name"),
            "last_name":                    kwargs.get("last_name"),
            "mobile_phone":                 kwargs.get("mobile_phone"),
            "date_of_birth":                kwargs.get("date_of_birth"),
            "gender":                       kwargs.get("gender"),
            "woreda":                       kwargs.get("woreda"),
            "kebele":                       kwargs.get("kebele"),
            "id_type":                      kwargs.get("id_type"),
            "id_number":                    kwargs.get("id_number"),
            "language":                     kwargs.get("language"),
            # Land and Crop
            "land_size_acres":              kwargs.get("land_size_acres"),
            "farm_id":                      kwargs.get("farm_id"),
            "farm_polygon":                 kwargs.get("farm_polygon"),
            "land_acreage":                 kwargs.get("land_acreage"),
            "farm_land_number":             kwargs.get("farm_land_number"),
            # Socio-Economic
            "marital_status":               kwargs.get("marital_status"),
            "size_of_family":               kwargs.get("size_of_family"),
            "number_of_children":           kwargs.get("number_of_children"),
            "no_of_females_family":         kwargs.get("no_of_females_family"),
            "no_of_males_family":           kwargs.get("no_of_males_family"),
            "family_member_owns_land":      kwargs.get("family_member_owns_land"),
            "source_of_income":             kwargs.get("source_of_income"),
            "education_level":              kwargs.get("education_level"),
            # Land Crop and Livestock
            "total_farmland_as_landowner":  kwargs.get("total_farmland_as_landowner"),
            "total_farmland_as_crop_sharing": kwargs.get("total_farmland_as_crop_sharing"),
            "total_farmland_as_rented":     kwargs.get("total_farmland_as_rented"),
            "certification_id":             kwargs.get("certification_id"),
            # Agronomic Data
            "farmland_size_hectares":       kwargs.get("farmland_size_hectares"),
            "land_ownership_status":        kwargs.get("land_ownership_status"),
            "soil_fertility_minerals":      kwargs.get("soil_fertility_minerals"),
            "moisture_levels":              kwargs.get("moisture_levels"),
        }

        try:
            for k, v in field_map.items():
                if v is not None and hasattr(doc, k):
                    setattr(doc, k, v)
            doc.current_step = max(getattr(doc, "current_step", 1), 5)
            doc.save(ignore_permissions=True)
            saved = {f: getattr(doc, f, None) for f in _FARMER_FIELDS}
            saved["application_id"] = doc.name
            saved["current_step"] = 5
            return success(saved)
        except Exception as e:
            return error("SAVE_FAILED", str(e))

    return error("INVALID_ACTION", f"Unknown action: {action}")


# ─── API: Get Farmer Details from Consent Data ─────────────────────────────

@frappe.whitelist(allow_guest=False)
def get_consent_data(**kwargs):
    """
    Returns formatted farmer details from the consent data stored on the Lead Application.
    Falls back to reading from the linked Consent Request doc if consent_data is missing.

    In the new A2C flow this is called after verify_otp_and_create has created the
    Lead Application and populated consent_data from OpenG2P.
    """
    kwargs = _parse_body(kwargs)
    application_id = kwargs.get("application_id")

    if not application_id:
        return error("MISSING_APP_ID", "application_id is required.")

    doc, err = _get_app(application_id, editable=False)
    if err:
        return err

    raw_data = None

    # --- Primary: read from consent_data saved by webhook ---
    if doc.consent_data:
        try:
            raw_data = json.loads(doc.consent_data) if isinstance(doc.consent_data, str) else doc.consent_data
        except Exception:
            raw_data = None

    # --- Fallback: consent_data missing (webhook not triggered / ID mismatch) ---
    #     Try to read whatever we stored on the linked Consent Request
    if not raw_data:
        consent_req_name = getattr(doc, "consent_request", None)
        if not consent_req_name:
            # Find the most recent Consent Request linked to this application
            linked = frappe.get_all(
                "Consent Request",
                filters={"loan_application": application_id},
                fields=["name", "openg2p_consent_id", "farmer_fayda_id", "status"],
                order_by="creation desc",
                limit=1,
            )
            if linked:
                consent_req_name = linked[0]["name"]

        if consent_req_name:
            cr = frappe.db.get_value(
                "Consent Request",
                consent_req_name,
                ["name", "openg2p_consent_id", "farmer_fayda_id", "status"],
                as_dict=True,
            )
            if cr:
                # Return a minimal response built from what we know
                return success({
                    "application_id": application_id,
                    "consent_status": cr.status or getattr(doc, "consent_status", None),
                    "farmer_details": {
                        "full_name": f"{getattr(doc, 'full_name', '')} {getattr(doc, 'last_name', '')}".strip() or None,
                        "fayda_id": cr.farmer_fayda_id,
                        "consent_status": cr.status,
                        "openg2p_consent_id": cr.openg2p_consent_id,
                        "consent_creation_request_id": cr.openg2p_consent_id,
                    },
                    "raw_consent_data": None,
                    "warning": (
                        "Webhook data not yet received from OpenG2P. "
                        "Farmer profile fields will be limited until the webhook fires. "
                        f"Consent status: {cr.status or 'Unknown'}"
                    ),
                })

        return error("NO_CONSENT_DATA", "Consent data not available yet. Please complete OTP verification.")

    try:
        # Support multiple webhook payload shapes from OpenG2P
        # Shape A: { "farmer": {...}, "selected_data": { "farmer": {...} }, "consent": {...} }
        # Shape B: { "data": { "farmer": {...} }, "consent": {...} }
        nested_data  = raw_data.get("data") or {}
        farmer_basic = raw_data.get("farmer") or nested_data.get("farmer") or {}
        selected     = (raw_data.get("selected_data") or {}).get("farmer") or {}
        consent_info = raw_data.get("consent") or nested_data.get("consent") or {}

        # Name: try various keys
        full_name = (
            farmer_basic.get("name")
            or farmer_basic.get("full_name")
            or f"{selected.get('given_name', '')} {selected.get('family_name', '')}".strip()
            or None
        )

        # Phone: phone_no may be a list or a string
        phone_raw = selected.get("phone_no") or farmer_basic.get("phone") or farmer_basic.get("mobile")
        if isinstance(phone_raw, list):
            mobile_phone = phone_raw[0] if phone_raw else None
        else:
            mobile_phone = phone_raw

        farmer_details = {
            "full_name":                    full_name,
            "given_name":                   selected.get("given_name") or farmer_basic.get("given_name"),
            "family_name":                  selected.get("family_name") or farmer_basic.get("family_name"),
            "mobile_phone":                 mobile_phone,
            "email":                        selected.get("email") or farmer_basic.get("email"),
            "gender":                       selected.get("gender") or farmer_basic.get("gender"),
            "date_of_birth":                selected.get("birthdate") or farmer_basic.get("date_of_birth"),
            "fayda_id":                     farmer_basic.get("id") or farmer_basic.get("fayda_id"),
            "consent_status":               doc.consent_status,
            "consent_creation_request_id":  consent_info.get("consent_creation_request_id"),
        }

        return success({
            "application_id": application_id,
            "consent_status": doc.consent_status,
            "farmer_details": farmer_details,
            "raw_consent_data": raw_data,
        })

    except Exception as e:
        return error("PARSE_ERROR", f"Failed to parse consent data: {str(e)}")

# ─── API 6: Application Manager ──────────────────────────────────────────────

def _build_tracking_timeline(doc):
    """Build the status tracking timeline used on the success screen."""
    status = getattr(doc, "status", "Draft")
    submitted_at = getattr(doc, "submitted_at", None)
    is_submitted = status not in ["Draft", "In Progress"]
    return [
        {
            "step": "Application Submitted",
            "description": "Securely transmitted to Cooperative Bank of Oromia via SFTP",
            "status": "Done" if is_submitted else "Pending",
            "timestamp": submitted_at,
        },
        {
            "step": "Under Review",
            "description": "Loan officer will verify documents and applicant details.",
            "status": "Done" if status in ["Approved", "Rejected", "Disbursed"] else "Pending",
            "timestamp": None,
        },
        {
            "step": "Credit Scoring",
            "description": "Automated credit assessment based on farm data and history.",
            "status": "Done" if status in ["Approved", "Rejected", "Disbursed"] else "Pending",
            "timestamp": None,
        },
        {
            "step": "Decision (Approved/Rejected)",
            "description": "Final approval or rejection communicated to applicant.",
            "status": "Done" if status in ["Approved", "Disbursed"] else ("Rejected" if status == "Rejected" else "Pending"),
            "timestamp": None,
        },
        {
            "step": "Loan Disbursed",
            "description": "Approved funds transferred to the farmer's bank account.",
            "status": "Done" if status == "Disbursed" else "Pending",
            "timestamp": None,
        },
    ]

@frappe.whitelist(allow_guest=False)
def application_manager(**kwargs):
    kwargs = _parse_body(kwargs)
    action = kwargs.get("action", "review")

    if action == "review":
        application_id = kwargs.get("application_id")
        doc, err = _get_app(application_id, editable=False)
        if err:
            return err

        has_docs = frappe.db.count("File", {
            "attached_to_doctype": "Loan Application",
            "attached_to_name": application_id,
        }) > 0

        consent_approved = getattr(doc, "consent_status", "") == "Approved"
        fayda_verified   = bool(getattr(doc, "fayda_verified", False))
        acknowledge_discrepancy = bool(getattr(doc, "acknowledge_discrepancy", False))
        current_step = getattr(doc, "current_step", 0)

        # UI Review accordion: 4 sections (Bank Details is NOT shown in the review screen)
        sections = [
            {
                "key": "loan_requirements",
                "label": "Loan Requirements",
                "description": "Capture information about the requested loan and farming activities.",
                "step": 1,
                "complete": current_step >= 1,
                "status_label": "Complete" if current_step >= 1 else "Incomplete",
            },
            {
                "key": "supporting_documents",
                "label": "Supporting Documents",
                "description": "Obtain farmer's consent to access registry data via Fayda OTP.",
                "step": 3,
                "complete": has_docs,
                "status_label": "Verified" if has_docs else "Missing",
            },
            {
                "key": "consent_otp_verification",
                "label": "Consent & OTP Verification",
                "description": "Capture information about the requested loan and farming activities.",
                "step": 4,
                "complete": consent_approved,
                "status_label": "Complete" if consent_approved else "Pending",
            },
            {
                "key": "farmer_details",
                "label": "Farmer Details",
                "description": "Capture information about the requested loan and farming activities.",
                "step": 5,
                "complete": current_step >= 5,
                "status_label": "Complete" if current_step >= 5 else "Incomplete",
            },
        ]

        can_submit = current_step >= 5 and consent_approved and has_docs

        return success({
            "sections": sections,
            "fayda_verified": fayda_verified,
            "acknowledge_discrepancy": acknowledge_discrepancy,
            "can_submit": can_submit,
            "application_id": application_id,
            "status": doc.status,
        })

    if action == "submit":
        application_id = kwargs.get("application_id")
        doc, err = _get_app(application_id)
        if err:
            return err

        # Consent is now verified at the Lead stage — no check needed here

        has_docs = frappe.db.count("File", {
            "attached_to_doctype": "Loan Application",
            "attached_to_name": application_id,
        }) > 0
        if not has_docs:
            return error("MISSING_DOCS", "At least one supporting document must be uploaded.")

        try:
            submitted_at = now_datetime()
            doc.status        = "Submitted"
            doc.current_step  = 6
            doc.submitted_at  = submitted_at
            doc.transfer_method = "SFTP Sync"
            doc.save(ignore_permissions=True)

            farmer_name = f"{getattr(doc, 'full_name', '')} {getattr(doc, 'last_name', '')}".strip()
            loan_type   = getattr(doc, "loan_type", "")
            loan_months = getattr(doc, "loan_duration_months", "")

            return success({
                "application_id": doc.name,
                "submitted_at":   submitted_at,
                "created_at":     str(doc.creation),
                "transfer_method": "SFTP Sync",
                "status": doc.status,
                "farmer_info": {
                    "farmer_name": farmer_name,
                    "loan_type":   loan_type,
                    "loan_duration_months": loan_months,
                    "display": f"{farmer_name} — {loan_type} • {loan_months} Months" if loan_type else farmer_name,
                },
                "tracking": _build_tracking_timeline(doc),
            })
        except Exception as e:
            return error("SUBMIT_FAILED", str(e))

    if action == "tracking":
        application_id = kwargs.get("application_id")
        doc, err = _get_app(application_id, editable=False)
        if err:
            return err
        return success({"tracking": _build_tracking_timeline(doc), "status": doc.status})

    if action == "draft":
        application_id = kwargs.get("application_id")
        step = kwargs.get("step")
        data = kwargs.get("data", {})

        doc, err = _get_app(application_id)
        if err:
            return err

        # Fields that must not be set via the generic draft endpoint
        PROTECTED_FIELDS = {"status", "loan_officer", "consent_status", "submitted_at",
                            "sftp_transmitted", "sftp_transmitted_at", "current_step"}
        try:
            if isinstance(data, str):
                data = json.loads(data)
            for k, v in data.items():
                if k in PROTECTED_FIELDS:
                    continue
                if hasattr(doc, k):
                    setattr(doc, k, v)
            doc.save(ignore_permissions=True)
            return success({"saved_at": now_datetime(), "step": step})
        except Exception as e:
            return error("DRAFT_SAVE_FAILED", str(e))

    if action == "cancel":
        application_id = kwargs.get("application_id")
        reason = kwargs.get("reason", "")
        doc, err = _get_app(application_id)
        if err:
            return err

        try:
            doc.status = "Cancelled"
            doc.cancellation_reason = reason
            doc.save(ignore_permissions=True)
            return success({"application_id": doc.name, "status": "Cancelled"})
        except Exception as e:
            return error("CANCEL_FAILED", str(e))

    if action == "update_status":
        application_id = kwargs.get("application_id")
        status = kwargs.get("status")
        remarks = kwargs.get("remarks", "")
        doc, err = _get_app(application_id, editable=False)
        if err:
            return err
        
        valid_statuses = ["Draft", "In Progress", "Submitted", "Under Review", "Approved", "Rejected", "Disbursed", "Cancelled"]
        if status not in valid_statuses:
            return error("INVALID_STATUS", f"status must be one of {valid_statuses}")
            
        try:
            doc.status = status
            doc.save(ignore_permissions=True)
            
            if remarks:
                comment = frappe.get_doc({
                    "doctype": "Comment",
                    "comment_type": "Comment",
                    "reference_doctype": "Loan Application",
                    "reference_name": application_id,
                    "content": f"Status updated to **{status}**.\n\nRemarks: {remarks}"
                })
                comment.insert(ignore_permissions=True)
                
            return success({"application_id": doc.name, "status": doc.status})
        except Exception as e:
            return error("UPDATE_FAILED", str(e))

    if action == "assign_owner":
        application_id = kwargs.get("application_id")
        loan_officer = kwargs.get("loan_officer")
        doc, err = _get_app(application_id, editable=False)
        if err:
            return err
            
        if not loan_officer or not frappe.db.exists("User", loan_officer):
            return error("INVALID_USER", "loan_officer must be a valid User email.")
            
        try:
            doc.loan_officer = loan_officer
            doc.save(ignore_permissions=True)
            return success({"application_id": doc.name, "loan_officer": doc.loan_officer})
        except Exception as e:
            return error("ASSIGN_FAILED", str(e))

    if action == "schedule_visit":
        application_id = kwargs.get("application_id")
        visit_date = kwargs.get("visit_date")
        visit_time = kwargs.get("visit_time")
        assigned_to = kwargs.get("assigned_to")
        
        doc, err = _get_app(application_id, editable=False)
        if err:
            return err
            
        if not visit_date or not visit_time or not assigned_to:
            return error("MISSING_FIELDS", "visit_date, visit_time, and assigned_to are required.")
            
        try:
            starts_on = f"{visit_date} {visit_time}"
            event = frappe.get_doc({
                "doctype": "Event",
                "subject": f"Farm Visit for {application_id}",
                "starts_on": starts_on,
                "event_type": "Public",
                "owner": assigned_to,
                "description": f"Scheduled visit for Loan Application {application_id}.\nRegion: {kwargs.get('region', '')}\nZone: {kwargs.get('zone', '')}\nWoreda: {kwargs.get('woreda', '')}\nKebele: {kwargs.get('kebele', '')}",
            })
            event.insert(ignore_permissions=True)
            
            comment = frappe.get_doc({
                "doctype": "Comment",
                "comment_type": "Info",
                "reference_doctype": "Loan Application",
                "reference_name": application_id,
                "content": f"Farm visit scheduled for {starts_on} assigned to {assigned_to}."
            })
            comment.insert(ignore_permissions=True)
            
            return success({
                "application_id": application_id,
                "event_id": event.name,
                "starts_on": starts_on,
                "assigned_to": assigned_to
            })
        except Exception as e:
            return error("SCHEDULE_FAILED", str(e))

    return error("INVALID_ACTION", f"Unknown action: {action}")

