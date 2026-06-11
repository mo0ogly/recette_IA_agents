# Typical Assets, Threats and Relevance (LIA-SEC SMSI)

Use this reference when users cannot identify their assets or which threats
apply. Suggest relevant entries from the context gathered in Step 2 of the
guided workflow. All asset records map to `smsi_assets.asset_type` =
`primary` (business value) or `support` (infrastructure).

## Primary assets (`asset_type: primary`) -- business data and processes

### Universal (all industries)
- Customer / client personal data
- Employee personal data
- Financial records
- Intellectual property / trade secrets
- Business contracts and agreements
- Corporate communications (email)

### Healthcare
- Patient health records (PHI / EHR)
- Medical device data
- Clinical trial data
- Prescription / medication records
- Insurance claims data

### Financial services
- Transaction records
- Account information
- Trading algorithms
- Credit scoring models
- Regulatory reports
- Customer financial profiles

### E-commerce / retail
- Payment card data
- Customer purchase history
- Inventory data
- Pricing information
- Supplier contracts

### Technology / SaaS
- Source code repositories
- API keys and secrets
- Customer usage data
- Product roadmaps
- Service configuration data

### Manufacturing / OT
- Product designs / CAD files
- Manufacturing processes
- Supply chain data
- Quality control records
- Equipment maintenance logs

### Public sector
- Citizen records
- Policy documents
- Classified information
- Grant / funding data
- Regulatory enforcement data

## Support assets (`asset_type: support`) -- infrastructure

### Small (1-50 employees)
- Cloud email (Microsoft 365 / Google Workspace)
- Cloud storage (OneDrive / Google Drive / Dropbox)
- Accounting software
- CRM system
- Company website
- Employee laptops / workstations
- Mobile devices (BYOD)
- Network router / firewall

### Medium (50-500 employees) -- all of Small, plus
- ERP system
- HR information system (HRIS)
- Cloud infrastructure (AWS / Azure / GCP)
- VPN / remote access
- Identity provider (SSO)
- Backup systems
- Database servers
- Development / test environments
- Endpoint protection platform
- Security monitoring tools

### Large (500+ employees) -- all of Medium, plus
- Data center infrastructure
- Mainframe systems
- SIEM platform
- Data lake / data warehouse
- API gateway
- Container orchestration (Kubernetes)
- CI/CD pipeline
- Service desk / ITSM platform
- Privileged access management
- Network segmentation infrastructure

### SaaS-heavy organizations
- Identity provider (SSO / IdP)
- Collaboration tools (chat, video conferencing)
- Project management
- Design tools
- Analytics platforms
- Marketing automation
- Customer support platform
- Document signing services

### Regulated environments (additions)
- Audit trail / logging systems
- Compliance management platform
- Data loss prevention (DLP)
- Encryption key management
- Access review systems
- Policy management platform

## CIA rating guidance (1-5)

Each asset carries `confidentiality_level`, `integrity_level`,
`availability_level` (integers 1-5, default 3). Suggested anchors:

| Level | Confidentiality | Integrity | Availability |
|-------|-----------------|-----------|--------------|
| 5 | Disclosure causes severe legal/financial harm (PII, secrets) | Corruption is catastrophic (financial ledgers) | Downtime halts the business (core DB) |
| 3 | Internal-only data | Errors are recoverable | Hours of downtime tolerable |
| 1 | Public data | Integrity not material | Long downtime acceptable |

## Threat catalogue (ISO 27005)

LIA-SEC ships its threat catalogue in the `iso27005_threats` table. Read it
live rather than assuming a fixed list:

```sql
SELECT id, ref_id, name FROM iso27005_threats ORDER BY ref_id;
```

Common threat families to map against assets:

| Threat family | Typical target assets |
|---------------|-----------------------|
| Ransomware | Customer data, databases, file storage |
| Phishing / spear phishing | Employee endpoints, corporate email |
| Data breach / leak / shadow IT | Customer data, source code, API keys |
| Cloud security threats | Cloud infrastructure, SaaS apps |
| API security threats | Application code, API gateway |
| Insider threats | API keys / secrets, source code |
| Supply chain / third-party attacks | CI/CD pipeline, dependencies |
| Password / brute-force attacks | Corporate email, admin accounts |
| Zero-day exploits | Internet-facing services, unpatched software |
| Advanced persistent threats (APT) | High-value primary assets |
| DoS / DDoS | Public-facing services, API gateway |
| Social engineering | Employees, finance team |
| Malware / spyware | Endpoints, servers |
| IoT / OT vulnerabilities | Industrial control systems, devices |
| AI / model manipulation | AI/ML systems, training data |
| Mobile device threats | BYOD, mobile endpoints |
| Physical security threats | Data center, on-prem hardware |
| System outage (failures, bugs) | Production database, core services |
| Disinformation / reputation attacks | Public communications, brand |
| Regulatory non-compliance | Customer data (GDPR / HIPAA / PCI / NIS2) |

## Vulnerability-to-CVE bridge (TruRisk)

Vulnerabilities live in `iso27005_vulnerabilities` and may carry a
`linked_cve_id`. When a scenario's vulnerability has a CVE, do NOT estimate
probability/impact by hand -- attach the CVE(s) to the scenario
(`linked_cve_ids`) and call:

```
POST /api/grc/iso27005/scenarios/{id}/suggest-risk
```

This returns a suggested probability/impact derived from CVSS + EPSS +
CISA KEV + exploit maturity, so the qualitative scenario inherits real,
defensible threat-intelligence scoring instead of a static relevance guess.

```sql
SELECT id, name, linked_cve_id
FROM iso27005_vulnerabilities
WHERE linked_cve_id IS NOT NULL;
```

## Scenario relevance template

For every suggested threat-asset pair, frame the scenario with:

```
[Threat] on [Asset]
Description: how the threat materializes against the asset.
Relevance: why it matters for THIS org -- regulation, business value,
exposure, CIA rating of the asset, linked CVEs if any.
```
