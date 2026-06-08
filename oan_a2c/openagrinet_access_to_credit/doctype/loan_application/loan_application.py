# Copyright (c) 2026, OpenAgriNet and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class LoanApplication(Document):
	pass

import frappe
from frappe.utils import cint
import math

@frappe.whitelist()
def get_loan_applications(search=None, status=None, loan_amount_min=None, loan_amount_max=None, loan_type=None, mobile_phone=None, from_date=None, to_date=None, page=1, page_size=20):
    try:
        # Check permissions
        if not frappe.has_permission("Loan Application", "read"):
            return {
                "status": "error",
                "message": "Not permitted to view Loan Applications"
            }

        page = cint(page) or 1
        page_size = cint(page_size) or 20
        offset = (page - 1) * page_size

        conditions = []
        values = {}

        # Apply role-based match conditions
        match_conditions = frappe.build_match_conditions("Loan Application")
        if match_conditions:
            conditions.append(f"({match_conditions})")

        # Apply search and filters
        if search:
            conditions.append("(application_id LIKE %(search)s OR full_name LIKE %(search)s OR last_name LIKE %(search)s)")
            values['search'] = f"%{search}%"
            
        if status:
            if isinstance(status, str) and status.startswith("["):
                import json
                try:
                    status_list = json.loads(status)
                    if isinstance(status_list, list) and status_list:
                        in_placeholders = ", ".join([f"%(status_{i})s" for i in range(len(status_list))])
                        conditions.append(f"status IN ({in_placeholders})")
                        for i, s in enumerate(status_list):
                            values[f"status_{i}"] = s
                except Exception:
                    conditions.append("status = %(status)s")
                    values['status'] = status
            elif isinstance(status, list) and status:
                in_placeholders = ", ".join([f"%(status_{i})s" for i in range(len(status))])
                conditions.append(f"status IN ({in_placeholders})")
                for i, s in enumerate(status):
                    values[f"status_{i}"] = s
            else:
                conditions.append("status = %(status)s")
                values['status'] = status

        if loan_amount_min is not None:
            conditions.append("requested_amount >= %(loan_amount_min)s")
            values['loan_amount_min'] = loan_amount_min

        if loan_amount_max is not None:
            conditions.append("requested_amount <= %(loan_amount_max)s")
            values['loan_amount_max'] = loan_amount_max

        if loan_type:
            conditions.append("loan_type = %(loan_type)s")
            values['loan_type'] = loan_type

        if mobile_phone:
            conditions.append("mobile_phone LIKE %(mobile_phone)s")
            values['mobile_phone'] = f"%{mobile_phone}%"

        if from_date:
            conditions.append("creation >= %(from_date)s")
            values['from_date'] = from_date
            
        if to_date:
            conditions.append("creation <= %(to_date)s")
            values['to_date'] = f"{to_date} 23:59:59"

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # 1. Total count for pagination
        count_query = f"""
            SELECT COUNT(name) as total
            FROM `tabLoan Application`
            {where_clause}
        """
        total_records = frappe.db.sql(count_query, values)[0][0] or 0
        total_pages = math.ceil(total_records / page_size) if total_records > 0 else 0

        # 2. Fetch paginated applications
        list_query = f"""
            SELECT 
                name, application_id, farmer, full_name, last_name, status, 
                requested_amount, loan_duration_months, primary_crop, 
                loan_type, submitted_at, creation,
                modified AS last_updated
            FROM `tabLoan Application`
            {where_clause}
            ORDER BY creation DESC
            LIMIT %(page_size)s OFFSET %(offset)s
        """
        values['page_size'] = page_size
        values['offset'] = offset
        
        recent_applications = frappe.db.sql(list_query, values, as_dict=True)

        return {
            "status": "success",
            "results": recent_applications,
            "pagination": {
                "total": total_records,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Loan Applications Error")
        return {
            "status": "error",
            "message": str(e)
        }

@frappe.whitelist()
def get_loan_summary():
    try:
        # Check permissions
        if not frappe.has_permission("Loan Application", "read"):
            return {
                "status": "error",
                "message": "Not permitted to view Loan Applications"
            }

        conditions = []
        # Apply role-based match conditions
        match_conditions = frappe.build_match_conditions("Loan Application")
        if match_conditions:
            conditions.append(f"({match_conditions})")

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        summary_query = f"""
            SELECT 
                COUNT(name) as total_applications,
                SUM(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN status IN ('Under Review', 'Submitted') THEN 1 ELSE 0 END) as pending_review,
                SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END) as rejected,
                SUM(CASE WHEN status = 'Draft' THEN 1 ELSE 0 END) as draft
            FROM `tabLoan Application`
            {where_clause}
        """
        summary_res = frappe.db.sql(summary_query, as_dict=True)
        summary_data = summary_res[0] if summary_res else {}

        return {
            "status": "success",
            "total": cint(summary_data.get("total_applications", 0)),
            "by_status": {
                "Approved": cint(summary_data.get("approved", 0)),
                "Under Review": cint(summary_data.get("pending_review", 0)),
                "Rejected": cint(summary_data.get("rejected", 0)),
                "Draft": cint(summary_data.get("draft", 0))
            }
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Loan Summary Error")
        return {
            "status": "error",
            "message": str(e)
        }
