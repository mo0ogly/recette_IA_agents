# Template ReportRule JSON - Reference Detaillee

## Structure Complete

Le fichier ReportRule contient la procedure de remediation experte.

### Convention de nommage du filename (CRITIQUE -- jamais `R-A-A-*`)

`A-` = **A**nalyse (regle YAML), `R-` = **R**emediation (ReportRule), la lettre
suivante = la CATEGORIE/axe (A=Architecture, S=Security, C=CGOV, H=HEAL, T=TRAC,
V=VULN, P=Privileged). Le filename ReportRule se derive de l'id YAML en REMPLACANT
le `A-` de tete par `R-` :

```
YAML id   : A-{CAT}-{nom}      ex: A-A-DC-Coerce  (Analyse + cat Architecture)
ReportRule: R-{CAT}-{nom}      ex: R-A-DC-Coerce  (Remediation + cat Architecture)
```

NE PAS prefixer `R-` a l'id complet (cela donne le double `R-A-A-DC-Coerce.json`,
INTERDIT). Remplacer le premier token. Le champ `rule_id` DANS le JSON reste l'id
YAML (`A-A-...`) pour la linkage ; seul le filename porte `R-{CAT}-{nom}`.

### Template CVE Rule

```json
{
  "rule_id": "A-VULN-{TECH}-CVE-{YEAR}-{NUMBER}",
  "title": "CVE-{YEAR}-{NUMBER} - {Description courte}",
  "technology": "{Technology}",
  "author": "LIA-Scan Rules Team",
  "date": "YYYY-MM-DD",
  "severity": "CRITICAL",
  "risk_level": "critical",
  "category": "Vulnerability Management",
  "description": "Description detaillee de la vulnerabilite, impact, et contexte.",
  "recommendation": "Mettre a jour vers la version X.Y.Z ou superieure.",
  "technical_context": "CVE-{YEAR}-{NUMBER} affecte {produit} versions anterieures a X.Y.Z. Score CVSS: 9.8. Exploite activement (CISA KEV).",
  "risk_factors": [
    "Execution de code arbitraire a distance",
    "Exploit public disponible (Metasploit/ExploitDB)",
    "CISA KEV - Exploitation active confirmee",
    "Score CVSS 9.8 CRITICAL"
  ],
  "cve_info": {
    "cve_id": "CVE-{YEAR}-{NUMBER}",
    "cvss_score": 9.8,
    "cvss_severity": "CRITICAL",
    "is_kev": true,
    "kev_date_added": "YYYY-MM-DD",
    "exploit_maturity": "WEAPONIZED",
    "epss_score": 0.95,
    "remediation_priority": "P0_EMERGENCY"
  },
  "affected_versions": {
    "product": "{Product Name}",
    "vendor": "{Vendor}",
    "branches": [
      {
        "branch": "7.6.x",
        "affected": "< 7.6.6",
        "fixed": "7.6.6"
      },
      {
        "branch": "7.4.x",
        "affected": "< 7.4.11",
        "fixed": "7.4.11"
      }
    ]
  },
  "compliance_references": {
    "pci_dss": [
      {
        "id": "6.3.3",
        "title": "Security patches",
        "version": "v4.0"
      }
    ],
    "nist_800_53": ["SI-2", "RA-5", "CM-3"],
    "iso_27001": ["A.12.6.1", "A.18.2.3"],
    "anssi": [
      {
        "id": "R14",
        "title": "Patch management"
      }
    ],
    "mitre_attack": [
      {
        "technique": "T1190",
        "tactic": "Initial Access",
        "name": "Exploit Public-Facing Application"
      }
    ]
  },
  "remediation": {
    "investigation": {
      "description": "Etapes d'investigation pour evaluer l'exposition",
      "steps": [
        {
          "step": 1,
          "action": "Identifier les systemes affectes",
          "command": "commande_specifique --check-version",
          "expected_output": "Version X.Y.Z ou inferieure = vulnerable",
          "interpretation": "Si version < X.Y.Z, le systeme est vulnerable"
        },
        {
          "step": 2,
          "action": "Verifier les indicateurs de compromission",
          "command": "commande_ioc_check",
          "expected_output": "Absence de IOCs",
          "interpretation": "Presence de IOCs = compromission potentielle"
        },
        {
          "step": 3,
          "action": "Evaluer l'exposition reseau",
          "command": "commande_network_check",
          "expected_output": "Service non expose sur internet",
          "interpretation": "Exposition internet = risque critique"
        }
      ]
    },
    "emergency_response": {
      "description": "Actions immediates de mitigation",
      "steps": [
        {
          "step": 1,
          "action": "Appliquer le patch de securite",
          "command": "commande_update --version X.Y.Z",
          "verification": "commande_verify --version",
          "risk": "Redemarrage du service necessaire",
          "rollback": "commande_rollback --to-version previous"
        },
        {
          "step": 2,
          "action": "Appliquer un workaround temporaire si patch impossible",
          "command": "commande_workaround",
          "verification": "commande_verify_workaround",
          "risk": "Fonctionnalite reduite",
          "rollback": "commande_undo_workaround"
        }
      ]
    },
    "prevention": {
      "description": "Mesures preventives long terme",
      "steps": [
        {
          "step": 1,
          "action": "Implementer un processus de patch management",
          "command": "Configuration automatique des mises a jour",
          "notes": "Delai max: 72h pour CRITICAL, 7j pour HIGH"
        },
        {
          "step": 2,
          "action": "Scanner regulierement les vulnerabilites",
          "command": "Scan de vulnerabilites hebdomadaire",
          "notes": "Integrer dans pipeline CI/CD si applicable"
        },
        {
          "step": 3,
          "action": "Segmentation reseau",
          "command": "Firewall rules pour limiter l'exposition",
          "notes": "Zero trust architecture recommandee"
        }
      ]
    },
    "long_term_remediation": {
      "steps": [
        "Audit de securite trimestriel",
        "Plan de gestion des vulnerabilites",
        "Formation equipes operations",
        "Revue architecture annuelle"
      ]
    }
  }
}
```

### Template BANK Compliance Rule

```json
{
  "rule_id": "A-{AXIS}-BANK-{COMPONENT}",
  "title": "Bank Security - {Description}",
  "technology": "Banking",
  "author": "LIA-Scan Rules Team",
  "date": "YYYY-MM-DD",
  "severity": "HIGH",
  "risk_level": "important",
  "category": "{Category}",
  "description": "Description de la non-conformite bancaire.",
  "recommendation": "Resume de la recommandation PCI/SWIFT.",
  "technical_context": "Contexte technique bancaire.",
  "risk_factors": [
    "Non-conformite PCI-DSS 4.0",
    "Risque de fraude/skimming",
    "Exposition donnees carte"
  ],
  "compliance_references": {
    "pci_dss": [
      {
        "id": "9.5",
        "title": "Physical device security",
        "version": "v4.0"
      }
    ],
    "pci_pts": [
      {
        "id": "B.8",
        "title": "USB port security",
        "version": "v7.0"
      }
    ],
    "iso_27001": ["A.11.2.4"],
    "anssi": [
      {
        "id": "R14",
        "title": "Security configuration"
      }
    ]
  },
  "remediation": {
    "investigation": {
      "steps": [
        {
          "step": 1,
          "action": "Identifier les equipements non conformes",
          "command": "Query systeme de gestion terminaux",
          "expected_output": "Liste equipements non conformes",
          "interpretation": "Chaque equipement = risque potentiel"
        }
      ]
    },
    "emergency_response": {
      "steps": [
        {
          "step": 1,
          "action": "Corriger la configuration",
          "command": "Commande de correction",
          "verification": "Commande de verification",
          "risk": "Impact operationnel a evaluer",
          "rollback": "Commande de retour arriere"
        }
      ]
    },
    "prevention": {
      "steps": [
        {
          "step": 1,
          "action": "Politique de securite documentee",
          "command": "Revue politique annuelle",
          "notes": "Conforme PCI-DSS 4.0 + PCI-PTS"
        }
      ]
    }
  }
}
```

## Champs Obligatoires ReportRule

| Champ | Obligatoire | Description |
|-------|-------------|-------------|
| `rule_id` | Oui | Doit matcher l'ID de la regle YAML |
| `title` | Oui | Titre descriptif en anglais |
| `technology` | Oui | Technologie ciblee |
| `severity` | Oui | CRITICAL, HIGH, MEDIUM, LOW |
| `description` | Oui | Description complete du probleme |
| `recommendation` | Oui | Resume de la recommandation |
| `remediation.investigation` | Oui | Etapes d'investigation (>= 2) |
| `remediation.emergency_response` | Oui | Actions correctives (>= 1) |
| `remediation.prevention` | Oui | Mesures preventives (>= 1) |
| `compliance_references` | Recommande | Mapping conformite |
| `risk_factors` | Recommande | Liste facteurs de risque |
| `cve_info` | CVE only | Metadata CVE si applicable |

## Priorites de Remediation

| Priorite | Delai | Criteres |
|----------|-------|----------|
| P0_EMERGENCY | 24h | CVSS >= 9.0 + KEV + exploit weaponized |
| P1_CRITICAL | 72h | CVSS >= 9.0 OU KEV |
| P2_HIGH | 7j | CVSS >= 7.0 |
| P3_MEDIUM | 30j | CVSS >= 4.0 |
| P4_LOW | 90j | CVSS < 4.0 |
