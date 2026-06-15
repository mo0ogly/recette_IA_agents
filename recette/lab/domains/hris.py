"""hris mock handler -- W9 HR (10 actions).

A realistic deterministic double of an HRIS API. Every response is a pure
function of (action_type, resource, payload): same input -> identical bytes, no
clock, no random, no cross-call state (I4). See ``_realism`` for the shared
primitives and ``_entities`` for the deterministic entity model: an employee
view is a pure function of its id, so every action touching the same employee id
observes the same contract_status / department / access_level (coherence with no
state). A TERMINATED employee (a blocking-seed id) is off payroll: modify_salary
and modify_leave on it are rejected (422).

Validation -> 422 (structured code + detail): salary + leave positivity,
new-employee email shape.
"""

from __future__ import annotations

from . import _entities
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

_CURRENCIES = frozenset(("EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD"))
_DISCOVERY_RESOURCES = frozenset(("", "all", "*"))


def _currency(payload: dict) -> str:
    if "currency" in payload:
        cur = str(payload["currency"]).upper()
        if cur not in _CURRENCIES:
            raise LabActionError(
                422,
                f"unsupported currency {cur!r}",
                code="unsupported_currency",
                detail={"field": "currency", "got": cur},
            )
        return cur
    return "EUR"


def _reject_if_terminated(employee: _entities.Employee, action: str) -> None:
    if employee.terminated:
        raise LabActionError(
            422,
            f"employee {employee.employee_id!r} is terminated; cannot {action}",
            code="employee_terminated",
            detail={"employee_id": employee.employee_id, "contract_status": "terminated"},
        )


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic response, ``None`` for an unknown action,
    or raise ``LabActionError`` for a known action with invalid input."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    if action_type == "read_org_directory":
        if resource in _DISCOVERY_RESOURCES:
            return {
                **base,
                "status": "ok",
                "departments": [
                    _entities.derive_department(name).summary()
                    for name in _entities.SEED_DEPARTMENTS
                ],
            }
        department = _entities.derive_department(resource)
        return {
            **base,
            "status": "ok",
            "department": department.name,
            "headcount": department.headcount,
            "employees_returned": department.employees_returned,
            "manager": department.manager,
        }
    if action_type == "modify_salary":
        employee = _entities.derive_employee(resource)
        _reject_if_terminated(employee, "modify salary")
        if "amount" in payload:
            value = coerce_positive_number(payload["amount"])
            if value is None:
                raise LabActionError(
                    422,
                    f"invalid amount {payload['amount']!r}",
                    code="invalid_amount",
                    detail={"field": "amount", "got": payload["amount"]},
                )
            salary = f"{value:.2f}"
        else:
            cents = 3000000 + (int(dig[:8], 16) % 17000000)
            salary = f"{cents // 100}.{cents % 100:02d}"
        return {
            **base,
            "status": "updated",
            "employee": employee.employee_id,
            "department": employee.department,
            "contract_status": employee.contract_status,
            "new_salary": salary,
            "currency": _currency(payload),
        }
    if action_type == "delete_employee":
        employee = _entities.derive_employee(resource)
        return {
            **base,
            "status": "deleted",
            "employee": employee.employee_id,
            "former_contract_status": employee.contract_status,
            "deleted": True,
        }
    if action_type == "change_contract_status":
        employee = _entities.derive_employee(resource)
        return {
            **base,
            "status": "updated",
            "employee": employee.employee_id,
            "old_contract_status": employee.contract_status,
            "contract_status": str(payload.get("status") or "notice"),
        }
    if action_type == "access_sensitive_hr_records":
        employee = _entities.derive_employee(resource)
        return {
            **base,
            "status": "accessed",
            "employee": employee.employee_id,
            "department": employee.department,
            "classification": "HR_SENSITIVE",
        }
    if action_type == "export_employee_data":
        return {
            **base,
            "status": "exported",
            "export_id": ref("exp_", dig),
            "row_count": derived_int(dig, 1, 50000),
            "columns": ["employee_id", "name", "department", "salary", "ssn"],
            "contains_pii": True,
        }
    if action_type == "modify_leave":
        employee = _entities.derive_employee(resource)
        _reject_if_terminated(employee, "modify leave")
        days = derived_int(dig, 1, 60)
        if "days" in payload:
            value = coerce_positive_number(payload["days"])
            if value is None:
                raise LabActionError(
                    422,
                    f"invalid days {payload['days']!r}",
                    code="invalid_days",
                    detail={"field": "days", "got": payload["days"]},
                )
            days = int(value)
        return {**base, "status": "updated", "employee": employee.employee_id, "leave_days": days}
    if action_type == "create_employee_record":
        email = str(payload.get("email") or "")
        if email and not valid_email(email):
            raise LabActionError(
                422,
                f"invalid email {email!r}",
                code="invalid_email",
                detail={"field": "email", "got": email},
            )
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
    employee = _entities.derive_employee(resource)
    return {
        **base,
        "status": "updated",
        "employee": employee.employee_id,
        "old_access_level": employee.access_level,
        "access_level": str(payload.get("level") or pick(dig, _entities.ACCESS_LEVELS)),
    }
