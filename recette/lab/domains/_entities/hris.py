"""HRIS lab entities: employees and departments (derived from id)."""

from __future__ import annotations

from dataclasses import dataclass

from ._common import _edigest, _int, _pick

__all__ = [
    "ACCESS_LEVELS",
    "CONTRACT_ACTIVE",
    "DEPARTMENTS",
    "SEED_DEPARTMENTS",
    "SEED_TERMINATED_EMPLOYEES",
    "Department",
    "Employee",
    "derive_department",
    "derive_employee",
]

CONTRACT_ACTIVE = ("active", "probation", "notice")
ACCESS_LEVELS = ("standard", "elevated", "admin")
DEPARTMENTS = ("engineering", "finance", "sales", "support", "legal")
SEED_DEPARTMENTS = ("engineering", "finance", "sales")
SEED_TERMINATED_EMPLOYEES = ("hris/emp/terminated-1",)


@dataclass(frozen=True)
class Employee:
    """An HRIS employee, fully derived from its id."""

    employee_id: str
    department: str
    contract_status: str
    access_level: str

    @property
    def terminated(self) -> bool:
        """A terminated employee is off payroll; salary/leave cannot change."""
        return self.contract_status == "terminated"


def derive_employee(employee_id: str) -> Employee:
    eid = employee_id or "hris/emp/unknown"
    dig = _edigest("employee", eid)
    status = "terminated" if eid in SEED_TERMINATED_EMPLOYEES else _pick(dig, CONTRACT_ACTIVE)
    return Employee(
        employee_id=eid,
        department=_pick(dig, DEPARTMENTS, offset=4),
        contract_status=status,
        access_level=_pick(dig, ACCESS_LEVELS, offset=8),
    )


@dataclass(frozen=True)
class Department:
    """An HRIS department directory view, fully derived from its name."""

    name: str
    headcount: int
    employees_returned: int
    manager: str

    def summary(self) -> dict:
        return {"name": self.name, "headcount": self.headcount, "manager": self.manager}


def derive_department(name: str) -> Department:
    dept = name or "all"
    dig = _edigest("department", dept)
    return Department(
        name=dept,
        headcount=_int(dig, 1, 20000),
        employees_returned=_int(dig, 1, 500, offset=8),
        manager=f"usr_{dig[:8]}",
    )
