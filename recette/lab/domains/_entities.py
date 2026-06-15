"""Deterministic entity model for lab doubles.

An entity (an invoice, a payee, an account, a supplier) is a PURE function of
its id: ``derive_invoice("inv/9")`` returns the same Invoice for every action
that touches ``inv/9``, this run and every replay. Cross-call coherence
therefore needs no mutable state (I4): two actions referencing the same id
observe the same entity because both recompute it from the id alone.

No clock, no random, no stored state. Time is expressed as a relative ordinal
(``due_in_days``), never a wall-clock date, so the model stays byte-stable under
replay. The same id always yields the same entity.

Seed tuples (``SEED_INVOICES`` ...) are a small set of KNOWN ids the doubles can
surface for discovery. They are not state -- they are constants. An arbitrary id
still derives a valid entity (any id works), seed ids just derive a richer one.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

INVOICE_STATES = ("paid", "pending", "overdue", "disputed")
CURRENCIES = ("EUR", "USD", "GBP", "CHF")

# Known ids surfaced for discovery (read with an empty/"all" resource lists them).
SEED_INVOICES = ("inv/2024-0001", "inv/2024-0002", "inv/2024-0003")
SEED_SUPPLIERS = ("supplier/acme", "supplier/globex", "supplier/initech")


def _edigest(kind: str, entity_id: str) -> str:
    """64-hex digest keyed ONLY on (kind, id) -- the coherence anchor.

    Independent of action_type/payload so every action touching the same entity
    derives the identical view (I4)."""
    return hashlib.sha256(f"entity:{kind}:{entity_id}".encode()).hexdigest()


def _pick(dig: str, choices: tuple[str, ...], *, offset: int = 0) -> str:
    window = dig[offset : offset + 4] or dig[:4]
    return choices[int(window, 16) % len(choices)]


def _int(dig: str, lo: int, hi: int, *, offset: int = 0) -> int:
    window = dig[offset : offset + 8] or dig[:8]
    return lo + (int(window, 16) % (hi - lo))


def _money(cents: int) -> str:
    """Format an integer number of cents as a fixed 2-decimal string."""
    return f"{cents // 100}.{cents % 100:02d}"


def _masked_iban(dig: str) -> str:
    """A deterministic masked IBAN placeholder (never a real account)."""
    return f"DE**{'*' * 14}{dig[:4].upper()}"


@dataclass(frozen=True)
class Invoice:
    """A finance invoice, fully derived from its id."""

    invoice_id: str
    status: str
    amount: str
    currency: str
    payee: str
    due_in_days: int
    lines: tuple[dict, ...]
    seeded: bool

    @property
    def refundable(self) -> bool:
        """A paid invoice is closed (refunds go through the credit-note flow)."""
        return self.status != "paid"

    def summary(self) -> dict:
        """A compact view for discovery listings."""
        return {
            "invoice_id": self.invoice_id,
            "invoice_status": self.status,
            "amount_due": self.amount,
            "currency": self.currency,
            "payee": self.payee,
        }


def _invoice_lines(dig: str, currency: str, count: int) -> tuple[tuple[dict, ...], int]:
    """Derive line items and the coherent total (in cents) they sum to."""
    lines: list[dict] = []
    total = 0
    for i in range(count):
        offset = 16 + i * 8
        qty = _int(dig, 1, 12, offset=offset)
        unit_cents = 500 + _int(dig, 0, 49500, offset=offset + 2)
        subtotal = qty * unit_cents
        total += subtotal
        lines.append(
            {
                "sku": f"SKU-{dig[offset : offset + 6].upper()}",
                "qty": qty,
                "unit_price": _money(unit_cents),
                "subtotal": _money(subtotal),
                "currency": currency,
            }
        )
    return tuple(lines), total


def derive_invoice(invoice_id: str) -> Invoice:
    """The Invoice for an id -- identical across actions and replays."""
    iid = invoice_id or "inv/unknown"
    dig = _edigest("invoice", iid)
    seeded = iid in SEED_INVOICES
    status = _pick(dig, INVOICE_STATES)
    currency = _pick(dig, CURRENCIES, offset=4)
    line_count = _int(dig, 2, 5, offset=8) if seeded else _int(dig, 1, 3, offset=8)
    lines, total = _invoice_lines(dig, currency, line_count)
    payee = f"{_pick(dig, ('ACME Ltd', 'Globex SA', 'Initech', 'Umbrella Corp'), offset=12)}"
    return Invoice(
        invoice_id=iid,
        status=status,
        amount=_money(total),
        currency=currency,
        payee=payee,
        due_in_days=_int(dig, 0, 60, offset=20),
        lines=lines,
        seeded=seeded,
    )


@dataclass(frozen=True)
class Account:
    """A finance account, fully derived from its id."""

    account_id: str
    holder: str
    iban: str
    currency: str
    balance: str

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "holder": self.holder,
            "iban": self.iban,
            "currency": self.currency,
            "balance": self.balance,
        }


def derive_account(account_id: str) -> Account:
    aid = account_id or "acct/unknown"
    dig = _edigest("account", aid)
    return Account(
        account_id=aid,
        holder=_pick(dig, ("Treasury", "Payroll", "Operations", "Reserve")),
        iban=_masked_iban(dig),
        currency=_pick(dig, CURRENCIES, offset=4),
        balance=_money(100000 + _int(dig, 0, 99000000, offset=8)),
    )


@dataclass(frozen=True)
class Supplier:
    """A finance supplier, fully derived from its id."""

    supplier_id: str
    name: str
    iban: str
    category: str
    seeded: bool

    def to_dict(self) -> dict:
        return {
            "supplier_id": self.supplier_id,
            "name": self.name,
            "iban": self.iban,
            "category": self.category,
        }


def derive_supplier(supplier_id: str) -> Supplier:
    sid = supplier_id or "supplier/unknown"
    dig = _edigest("supplier", sid)
    return Supplier(
        supplier_id=sid,
        name=_pick(dig, ("ACME Ltd", "Globex SA", "Initech", "Umbrella Corp")),
        iban=_masked_iban(dig),
        category=_pick(dig, ("hardware", "services", "logistics", "software"), offset=4),
        seeded=sid in SEED_SUPPLIERS,
    )


# --- crm -----------------------------------------------------------------
# A behavioural state is assigned ONLY to ids in an explicit "blocking seed"
# set, so an arbitrary id (a probe, a fresh scenario id) is always actionable;
# the state-machine rejection is demonstrated through the seed ids.
CONTACT_LIFECYCLE = ("lead", "mql", "sql", "customer", "churned")
DEAL_STAGES_OPEN = ("prospecting", "qualification", "proposal", "negotiation")
ACCOUNT_TIERS = ("smb", "mid", "enterprise", "strategic")
SEED_CONTACTS = ("crm/contact/alice", "crm/contact/bob", "crm/contact/carol")
SEED_CLOSED_OPPORTUNITIES = ("crm/opp/closed-1",)


@dataclass(frozen=True)
class Contact:
    """A CRM contact, fully derived from its id."""

    contact_id: str
    account: str
    email: str
    lifecycle_stage: str
    owner: str
    seeded: bool

    def summary(self) -> dict:
        return {
            "contact_id": self.contact_id,
            "account": self.account,
            "email": self.email,
            "lifecycle_stage": self.lifecycle_stage,
        }


def _local_part(entity_id: str) -> str:
    tail = entity_id.split(":")[-1].split("/")[-1] or "contact"
    return tail.replace(" ", ".").lower()[:24]


def derive_contact(contact_id: str) -> Contact:
    cid = contact_id or "crm/contact/unknown"
    dig = _edigest("contact", cid)
    return Contact(
        contact_id=f"cnt_{dig[:10]}",
        account=cid,
        email=f"{_local_part(cid)}.{dig[:6]}@example-corp.test",
        lifecycle_stage=_pick(dig, CONTACT_LIFECYCLE),
        owner=f"usr_{dig[10:18]}",
        seeded=cid in SEED_CONTACTS,
    )


@dataclass(frozen=True)
class Opportunity:
    """A CRM opportunity, fully derived from its id."""

    opportunity_id: str
    stage: str
    amount: str
    currency: str
    account: str

    @property
    def closed(self) -> bool:
        """A closed-won opportunity is settled; its amount cannot be changed."""
        return self.stage == "closed_won"


def derive_opportunity(opportunity_id: str) -> Opportunity:
    oid = opportunity_id or "crm/opp/unknown"
    dig = _edigest("opportunity", oid)
    stage = "closed_won" if oid in SEED_CLOSED_OPPORTUNITIES else _pick(dig, DEAL_STAGES_OPEN)
    cents = 100000 + int(dig[:8], 16) % 9900000
    return Opportunity(
        opportunity_id=oid,
        stage=stage,
        amount=_money(cents),
        currency=_pick(dig, CURRENCIES, offset=8),
        account=f"acct_{dig[10:16]}",
    )


@dataclass(frozen=True)
class SalesAccount:
    """A CRM account, fully derived from its id (current owner + tier)."""

    account_id: str
    name: str
    owner: str
    tier: str


def derive_sales_account(account_id: str) -> SalesAccount:
    aid = account_id or "crm/account/unknown"
    dig = _edigest("sales_account", aid)
    return SalesAccount(
        account_id=aid,
        name=_pick(dig, ("ACME Ltd", "Globex SA", "Initech", "Umbrella Corp")),
        owner=f"usr_{dig[:8]}",
        tier=_pick(dig, ACCOUNT_TIERS, offset=4),
    )


# --- hris ----------------------------------------------------------------
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


# --- legal_dms -----------------------------------------------------------
DOC_TYPES = ("contract", "nda", "filing", "evidence", "memo")
CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")
SEED_POLICIES = ("legal/policy/privacy", "legal/policy/retention", "legal/policy/aml")
SEED_HELD_DOCUMENTS = ("legal/doc/hold-1",)


@dataclass(frozen=True)
class Policy:
    """A legal policy, fully derived from its id."""

    policy_id: str
    version: str
    state: str
    owner: str

    def summary(self) -> dict:
        return {"policy_id": self.policy_id, "version": self.version, "state": self.state}


def derive_policy(policy_id: str) -> Policy:
    pid = policy_id or "legal/policy/unknown"
    dig = _edigest("policy", pid)
    return Policy(
        policy_id=pid,
        version=f"v{_int(dig, 1, 20)}",
        state="published",
        owner=f"usr_{dig[:8]}",
    )


@dataclass(frozen=True)
class LegalDocument:
    """A legal document, fully derived from its id."""

    document_id: str
    doc_type: str
    classification: str
    on_hold: bool

    @property
    def deletable(self) -> bool:
        """A document under legal hold cannot be deleted (evidence preservation)."""
        return not self.on_hold


def derive_document(document_id: str) -> LegalDocument:
    did = document_id or "legal/doc/unknown"
    dig = _edigest("document", did)
    return LegalDocument(
        document_id=did,
        doc_type=_pick(dig, DOC_TYPES),
        classification=_pick(dig, CLASSIFICATIONS, offset=4),
        on_hold=did in SEED_HELD_DOCUMENTS,
    )


# --- support_desk --------------------------------------------------------
PRIORITIES = ("low", "normal", "high", "urgent")
TICKET_STATES_MUTABLE = ("open", "pending", "on_hold", "solved")
SEED_TICKETS = ("support/ticket/t-1001", "support/ticket/t-1002")
SEED_CLOSED_TICKETS = ("support/ticket/closed-1",)


@dataclass(frozen=True)
class Ticket:
    """A support ticket, fully derived from its id."""

    ticket_id: str
    priority: str
    state: str
    requester: str
    vip: bool

    @property
    def mutable(self) -> bool:
        """A closed ticket is immutable; reopen it before changing its status."""
        return self.state != "closed"

    def summary(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "priority": self.priority,
            "state": self.state,
            "vip": self.vip,
        }


def derive_ticket(ticket_id: str) -> Ticket:
    tid = ticket_id or "support/ticket/unknown"
    dig = _edigest("ticket", tid)
    state = "closed" if tid in SEED_CLOSED_TICKETS else _pick(dig, TICKET_STATES_MUTABLE, offset=4)
    return Ticket(
        ticket_id=tid,
        priority=_pick(dig, PRIORITIES),
        state=state,
        requester=f"cust_{dig[:8]}",
        vip=tid in SEED_TICKETS,
    )


# --- cloud ---------------------------------------------------------------
CLOUD_STATES = ("running", "stopped")
CLOUD_KINDS = ("ec2", "rds", "s3", "eks", "lambda")
CLOUD_REGIONS = ("eu-west-1", "us-east-1", "ap-south-1")
SEED_CLOUD_RESOURCES = ("cloud/res/db-prod", "cloud/res/bucket-logs", "cloud/res/eks-main")
SEED_TERMINATED_RESOURCES = ("cloud/res/terminated-1",)


@dataclass(frozen=True)
class CloudResource:
    """A cloud resource, fully derived from its id."""

    resource_id: str
    kind: str
    state: str
    region: str

    @property
    def terminated(self) -> bool:
        """A terminated resource is gone; it cannot be modified or deleted."""
        return self.state == "terminated"

    def summary(self) -> dict:
        return {"resource_id": self.resource_id, "kind": self.kind, "state": self.state}


def derive_cloud_resource(resource_id: str) -> CloudResource:
    rid = resource_id or "cloud/res/unknown"
    dig = _edigest("cloud_resource", rid)
    state = "terminated" if rid in SEED_TERMINATED_RESOURCES else _pick(dig, CLOUD_STATES)
    return CloudResource(
        resource_id=rid,
        kind=_pick(dig, CLOUD_KINDS, offset=4),
        state=state,
        region=_pick(dig, CLOUD_REGIONS, offset=8),
    )


# --- slack ---------------------------------------------------------------
SEED_CHANNELS = ("slack/channel/general", "slack/channel/random", "slack/channel/eng")
SEED_ARCHIVED_CHANNELS = ("slack/channel/archived-1",)


@dataclass(frozen=True)
class SlackChannel:
    """A Slack channel, fully derived from its id/name."""

    channel_id: str
    name: str
    is_private: bool
    num_members: int
    archived: bool

    def summary(self) -> dict:
        return {"channel_id": self.channel_id, "name": self.name, "archived": self.archived}


def derive_channel(name: str) -> SlackChannel:
    ch = name or "slack/channel/unknown"
    dig = _edigest("slack_channel", ch)
    return SlackChannel(
        channel_id=f"C{dig[:9].upper()}",
        name=ch,
        is_private=False,
        num_members=_int(dig, 1, 5000),
        archived=ch in SEED_ARCHIVED_CHANNELS,
    )


# --- product_cms ---------------------------------------------------------
CONTENT_STATES = ("draft", "in_review", "published")
SEED_CONTENT = ("cms/content/home", "cms/content/pricing", "cms/content/blog")
SEED_ARCHIVED_CONTENT = ("cms/content/archived-1",)


@dataclass(frozen=True)
class Content:
    """A CMS content item, fully derived from its id."""

    content_id: str
    state: str
    version: str
    word_count: int

    @property
    def archived(self) -> bool:
        """Archived content is read-only; edit/publish/delete is rejected."""
        return self.state == "archived"

    def summary(self) -> dict:
        return {"content_id": self.content_id, "state": self.state, "version": self.version}


def derive_content(content_id: str) -> Content:
    cid = content_id or "cms/content/unknown"
    dig = _edigest("content", cid)
    state = "archived" if cid in SEED_ARCHIVED_CONTENT else _pick(dig, CONTENT_STATES)
    return Content(
        content_id=cid,
        state=state,
        version=f"v{_int(dig, 1, 50)}",
        word_count=_int(dig, 10, 5000, offset=8),
    )


# --- data_platform -------------------------------------------------------
DATA_CLASS = ("public", "internal", "confidential", "restricted")
SEED_DATASETS = ("data/dataset/curated-sales", "data/dataset/curated-ops")
SEED_FROZEN_DATASETS = ("data/dataset/frozen-1",)


@dataclass(frozen=True)
class Dataset:
    """A data-platform dataset, fully derived from its id."""

    dataset_id: str
    classification: str
    row_estimate: int
    frozen: bool

    @property
    def available(self) -> bool:
        """A frozen/quarantined dataset cannot be queried or exported."""
        return not self.frozen

    def summary(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "classification": self.classification,
            "frozen": self.frozen,
        }


def derive_dataset(dataset_id: str) -> Dataset:
    did = dataset_id or "data/dataset/unknown"
    dig = _edigest("dataset", did)
    return Dataset(
        dataset_id=did,
        classification=_pick(dig, DATA_CLASS),
        row_estimate=_int(dig, 0, 1000000, offset=8),
        frozen=did in SEED_FROZEN_DATASETS,
    )


# --- github / gitlab -----------------------------------------------------
# Visibility/default_branch stay literal ("private"/"main") because the read
# handlers assert them; ``archived`` is the entity's behavioural state.
SEED_REPOS = ("github/repo/app", "github/repo/infra")
SEED_ARCHIVED_REPOS = ("github/repo/archived-1",)
SEED_PROJECTS = ("gitlab/project/app", "gitlab/project/infra")
SEED_ARCHIVED_PROJECTS = ("gitlab/project/archived-1",)


@dataclass(frozen=True)
class Repository:
    """A GitHub repository, fully derived from its full name."""

    full_name: str
    visibility: str
    default_branch: str
    archived: bool

    def summary(self) -> dict:
        return {"full_name": self.full_name, "archived": self.archived}


def derive_repository(full_name: str) -> Repository:
    name = full_name or "github/repo/unknown"
    return Repository(
        full_name=name,
        visibility="private",
        default_branch="main",
        archived=name in SEED_ARCHIVED_REPOS,
    )


@dataclass(frozen=True)
class GitlabProject:
    """A GitLab project, fully derived from its path."""

    path_with_namespace: str
    visibility: str
    default_branch: str
    archived: bool

    def summary(self) -> dict:
        return {"path_with_namespace": self.path_with_namespace, "archived": self.archived}


def derive_project(path: str) -> GitlabProject:
    p = path or "gitlab/project/unknown"
    return GitlabProject(
        path_with_namespace=p,
        visibility="private",
        default_branch="main",
        archived=p in SEED_ARCHIVED_PROJECTS,
    )


# --- mcp -----------------------------------------------------------------
SEED_TOOLS = ("web_search", "code_interpreter", "file_search")
SEED_DISABLED_TOOLS = ("mcp/tool/disabled-1", "disabled_tool")


@dataclass(frozen=True)
class McpTool:
    """An MCP tool, fully derived from its name."""

    tool: str
    registered: bool
    enabled: bool

    @property
    def usable(self) -> bool:
        """A disabled/unregistered tool cannot be invoked."""
        return self.registered and self.enabled


def derive_tool(tool: str) -> McpTool:
    name = tool or "mcp/tool/unknown"
    disabled = name in SEED_DISABLED_TOOLS
    return McpTool(tool=name, registered=not disabled, enabled=not disabled)
