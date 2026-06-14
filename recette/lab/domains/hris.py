"""hris mock handler -- W9 HR (10 actions).

A realistic deterministic double of an HRIS API. Every response is a pure
function of (action_type, resource, payload): same input -> identical bytes, no
clock, no random, no cross-call state (I4). See ``_realism`` for the shared
primitives and the validation contract.

Realism: HR objects per action (org directory headcount, salary change, employee
deletion, contract status, sensitive-record access, employee-data export with
PII, leave change, new employee record, official comm, access-rights change).
Validation -> 422: salary + leave positivity, new-employee email shape.
"""

from __future__ import annotations

from ._realism import (
    LabActionError,
    coerce_positive_number,
    derived_int,
    digest,
    envelope,
    pick,
    ref,
    valid_email,
)

_DOMAIN = "hris"

_KNOWN_ACTIONS = frozenset(
    (
        "read_org_directory",
        "modify_salary",
        "delete_employee",
        "change_contract_status",
        "access_sensitive_hr_records",
        "export_employee_data",
        "modify_leave",
        "create_employee_record",
        "send_official_hr_comm",
        "modify_employee_access_rights",
    )
)

_CONTRACT = ("active", "probation", "notice", "terminated")
_ACCESS = ("standard", "elevated", "admin")
_CURRENCIES = frozenset(("EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD"))


def _currency(payload: dict) -> str:
    if "currency" in payload:
        cur = str(payload["currency"]).upper()
        if cur not in _CURRENCIES:
            raise LabActionError(422, f"unsupported currency {cur!r}")
        return cur
    return "EUR"


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic response, ``None`` for an unknown action,
    or raise ``LabActionError`` for a known action with invalid input."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    if action_type == "read_org_directory":
        return {
            **base,
            "status": "ok",
            "department": resource,
            "headcount": derived_int(dig, 1, 20000),
            "employees_returned": derived_int(dig, 1, 500, offset=8),
        }
    if action_type == "modify_salary":
        if "amount" in payload:
            value = coerce_positive_number(payload["amount"])
            if value is None:
                raise LabActionError(422, f"invalid amount {payload['amount']!r}")
            salary = f"{value:.2f}"
        else:
            cents = 3000000 + (int(dig[:8], 16) % 17000000)
            salary = f"{cents // 100}.{cents % 100:02d}"
        return {
            **base,
            "status": "updated",
            "employee": resource,
            "new_salary": salary,
            "currency": _currency(payload),
        }
    if action_type == "delete_employee":
        return {**base, "status": "deleted", "employee": resource, "deleted": True}
    if action_type == "change_contract_status":
        return {
            **base,
            "status": "updated",
            "employee": resource,
            "contract_status": str(payload.get("status") or pick(dig, _CONTRACT)),
        }
    if action_type == "access_sensitive_hr_records":
        return {
            **base,
            "status": "accessed",
            "employee": resource,
            "classification": "HR_SENSITIVE",
        }
    if action_type == "export_employee_data":
        return {
            **base,
            "status": "exported",
            "export_id": ref("exp_", dig),
            "row_count": derived_int(dig, 1, 50000),
            "contains_pii": True,
        }
    if action_type == "modify_leave":
        days = derived_int(dig, 1, 60)
        if "days" in payload:
            value = coerce_positive_number(payload["days"])
            if value is None:
                raise LabActionError(422, f"invalid days {payload['days']!r}")
            days = int(value)
        return {**base, "status": "updated", "employee": resource, "leave_days": days}
    if action_type == "create_employee_record":
        email = str(payload.get("email") or "")
        if email and not valid_email(email):
            raise LabActionError(422, f"invalid email {email!r}")
        return {
            **base,
            "status": "created",
            "employee_id": ref("emp_", dig),
            "email": email or f"new.hire.{dig[:6]}@example-corp.test",
        }
    if action_type == "send_official_hr_comm":
        return {
            **base,
            "status": "sent",
            "comm_id": ref("comm_", dig),
            "audience": str(payload.get("audience") or "all-staff"),
        }
    # modify_employee_access_rights
    return {
        **base,
        "status": "updated",
        "employee": resource,
        "access_level": str(payload.get("level") or pick(dig, _ACCESS)),
    }
