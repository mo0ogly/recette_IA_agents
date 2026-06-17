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

This package was split by domain from a single module; the public surface is
preserved here verbatim, so ``from . import _entities`` and every
``_entities.derive_*`` / ``_entities.<Entity>`` / ``_entities.SEED_*`` reference
keeps working unchanged.
"""

from __future__ import annotations

# Shared primitives (kept importable as part of the historical module surface).
from ._common import _edigest, _int, _masked_iban, _money, _pick
from .cloud import (
    CLOUD_KINDS,
    CLOUD_REGIONS,
    CLOUD_STATES,
    SEED_CLOUD_RESOURCES,
    SEED_TERMINATED_RESOURCES,
    CloudResource,
    derive_cloud_resource,
)
from .crm import (
    ACCOUNT_TIERS,
    CONTACT_LIFECYCLE,
    DEAL_STAGES_OPEN,
    SEED_CLOSED_OPPORTUNITIES,
    SEED_CONTACTS,
    Contact,
    Opportunity,
    SalesAccount,
    derive_contact,
    derive_opportunity,
    derive_sales_account,
)
from .data_platform import (
    DATA_CLASS,
    SEED_DATASETS,
    SEED_FROZEN_DATASETS,
    Dataset,
    derive_dataset,
)
from .finance import (
    CURRENCIES,
    INVOICE_STATES,
    SEED_INVOICES,
    SEED_SUPPLIERS,
    Account,
    Invoice,
    Supplier,
    derive_account,
    derive_invoice,
    derive_supplier,
)
from .git import (
    SEED_ARCHIVED_PROJECTS,
    SEED_ARCHIVED_REPOS,
    SEED_PROJECTS,
    SEED_REPOS,
    GitlabProject,
    Repository,
    derive_project,
    derive_repository,
)
from .hris import (
    ACCESS_LEVELS,
    CONTRACT_ACTIVE,
    DEPARTMENTS,
    SEED_DEPARTMENTS,
    SEED_TERMINATED_EMPLOYEES,
    Department,
    Employee,
    derive_department,
    derive_employee,
)
from .legal import (
    CLASSIFICATIONS,
    DOC_TYPES,
    SEED_HELD_DOCUMENTS,
    SEED_POLICIES,
    LegalDocument,
    Policy,
    derive_document,
    derive_policy,
)
from .mcp import (
    SEED_DISABLED_TOOLS,
    SEED_TOOLS,
    McpTool,
    derive_tool,
)
from .product_cms import (
    CONTENT_STATES,
    SEED_ARCHIVED_CONTENT,
    SEED_CONTENT,
    Content,
    derive_content,
)
from .slack import (
    SEED_ARCHIVED_CHANNELS,
    SEED_CHANNELS,
    SlackChannel,
    derive_channel,
)
from .support import (
    PRIORITIES,
    SEED_CLOSED_TICKETS,
    SEED_TICKETS,
    TICKET_STATES_MUTABLE,
    Ticket,
    derive_ticket,
)

__all__ = [
    # common helpers
    "_edigest",
    "_pick",
    "_int",
    "_money",
    "_masked_iban",
    # finance
    "INVOICE_STATES",
    "CURRENCIES",
    "SEED_INVOICES",
    "SEED_SUPPLIERS",
    "Invoice",
    "Account",
    "Supplier",
    "derive_invoice",
    "derive_account",
    "derive_supplier",
    # crm
    "CONTACT_LIFECYCLE",
    "DEAL_STAGES_OPEN",
    "ACCOUNT_TIERS",
    "SEED_CONTACTS",
    "SEED_CLOSED_OPPORTUNITIES",
    "Contact",
    "Opportunity",
    "SalesAccount",
    "derive_contact",
    "derive_opportunity",
    "derive_sales_account",
    # hris
    "CONTRACT_ACTIVE",
    "ACCESS_LEVELS",
    "DEPARTMENTS",
    "SEED_DEPARTMENTS",
    "SEED_TERMINATED_EMPLOYEES",
    "Employee",
    "Department",
    "derive_employee",
    "derive_department",
    # legal
    "DOC_TYPES",
    "CLASSIFICATIONS",
    "SEED_POLICIES",
    "SEED_HELD_DOCUMENTS",
    "Policy",
    "LegalDocument",
    "derive_policy",
    "derive_document",
    # support
    "PRIORITIES",
    "TICKET_STATES_MUTABLE",
    "SEED_TICKETS",
    "SEED_CLOSED_TICKETS",
    "Ticket",
    "derive_ticket",
    # cloud
    "CLOUD_STATES",
    "CLOUD_KINDS",
    "CLOUD_REGIONS",
    "SEED_CLOUD_RESOURCES",
    "SEED_TERMINATED_RESOURCES",
    "CloudResource",
    "derive_cloud_resource",
    # slack
    "SEED_CHANNELS",
    "SEED_ARCHIVED_CHANNELS",
    "SlackChannel",
    "derive_channel",
    # product_cms
    "CONTENT_STATES",
    "SEED_CONTENT",
    "SEED_ARCHIVED_CONTENT",
    "Content",
    "derive_content",
    # data_platform
    "DATA_CLASS",
    "SEED_DATASETS",
    "SEED_FROZEN_DATASETS",
    "Dataset",
    "derive_dataset",
    # git
    "SEED_REPOS",
    "SEED_ARCHIVED_REPOS",
    "SEED_PROJECTS",
    "SEED_ARCHIVED_PROJECTS",
    "Repository",
    "GitlabProject",
    "derive_repository",
    "derive_project",
    # mcp
    "SEED_TOOLS",
    "SEED_DISABLED_TOOLS",
    "McpTool",
    "derive_tool",
]
