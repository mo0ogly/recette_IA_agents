# Structure OpenClaw — Reference

## Workspaces

```
~/.openclaw/
├── openclaw.json              # Config principale (agents, bindings, auth)
├── node.json                  # ACP node host (pairingToken, nodeId)
├── devices/paired.json        # Devices apparies (source du pairingToken)
├── workspace-{agent}/
│   ├── SOUL.md                # Personnalite, workflow, gates (editer avec /openclaw-soul)
│   ├── USER.md                # Contexte projet (stack, chemins, commandes)
│   ├── AGENTS.md              # Regles comportement general + routing LIA-SEC
│   ├── TOOLS.md               # Details outils locaux
│   ├── MEMORY.md              # Memoire long terme agent
│   ├── HEARTBEAT.md           # Taches a verifier lors des heartbeats
│   ├── knowledge/             # Docs projet (hard-links vers _alire/)
│   └── skills/                # Skills specifiques a l'agent
└── agents/                    # Sessions agents actives
```

## Mapping agents -> rooms Matrix

| Agent | Workspace | Room nom | Room ID Matrix |
|-------|-----------|----------|----------------|
| sigma-prime | workspace-sigma-prime | lia-general | !jZ3CrxfdTOxraqtP8e5irNT4yfjL1nw04p8hTXTWU0g |
| atlas | workspace-lia-architect | lia-atlas | !MMq1L9o9u23fBcNjIXhALNOA0FgXz9rtROIAw372O-U |
| hermes | workspace-lia-rd | lia-hermes | !psberIUZdZyRmO42ONIXrF4Jk0w846g0wpyvTLKyHmA |
| argus | workspace-lia-recette | lia-argus | !K5pv_8CIw5jvFgfHQMjEIJlvMhyJgMg3skNFVFwQp4g |
| forge-go | workspace-forge-go | lia-forge-go | !xTZwg8ik4J6hKJESLTkocMZPvA6b8-dRPCbuUm4AHBo |
| forge-react | workspace-forge-react | lia-forge-react | !CKglskidP4-QamU52mr03EA91FCLNBO9E316u3a_zMo |
| hawk | workspace-lia-auditeur | lia-hawk | !llZJ1QoSox5daezbbLWfX4mUijJxdk00z09DDqGANBU |
| nexus | workspace-lia-compliance | lia-nexus | !2mTxyNdK9svomdAawO3itNL9Aq-JiU5lcljWQwCNooU |
| probe | workspace-probe | lia-probe | !PRY-MC01WOa7vY-ba-o-KIzhUYt-q1dj8GV_oJY48IA |
| oracle | workspace-oracle | lia-oracle | !Vnk5AWTH1iwQmf913QXAyVyMJWSRIMXfuP3WHBuW1Y4 |

## Envoyer un message Matrix depuis exec

```json
{
  "tool": "exec",
  "command": "openclaw message send --channel matrix --target 'ROOM_ID' --message 'texte du message'",
  "workdir": "/home/mo0ogly/Bureau/vscode_lia_audit"
}
```

Exemple — HERMES notifie ARGUS apres creation de regle :
```json
{
  "tool": "exec",
  "command": "openclaw message send --channel matrix --target '!K5pv_8CIw5jvFgfHQMjEIJlvMhyJgMg3skNFVFwQp4g' --message 'Regle creee : CVE-2025-22462 (IVANTI). Chemin : lia_rules/rule_analysis/IVANTI/VULN/A-VULN-IVAN-ITSM-CVE-2025-22462/. Lancer validation.'",
  "workdir": "/home/mo0ogly/Bureau/vscode_lia_audit"
}
```

## Agents avec exec active

- hermes (lia-rd) : workflow CVE autonome
- argus (lia-recette) : workflow validation autonome
- sigma-prime : coordination + status

## Chemins projet LIA-Scan

```
BASE=/home/mo0ogly/Bureau/vscode_lia_audit
RULES=$BASE/lia_rules/rule_analysis/
RECETTE=$BASE/recette/
SKILLS=$BASE/.claude/skills/
ENGINE=$BASE/bin/lia_scan_engine
SCRIPTS=$BASE/scripts/collect/
```

## Commandes maintenance OpenClaw

```bash
openclaw status
openclaw nodes status          # doit afficher "paired · connected"
systemctl --user status openclaw
systemctl --user restart openclaw
openclaw agents bindings
openclaw channels status
```

## Technologies LIA-Scan par code

| Code | Description |
|------|-------------|
| ADDS | Active Directory / Windows LDAP / NTLM / Kerberos |
| EXCHANGE | Microsoft Exchange |
| IVANTI | Ivanti EPM / ICS / ITSM |
| CISC | Cisco IOS / SDWAN / ISE |
| DB12 | Debian 12 |
| OL09 | Oracle Linux 9 |
| UB22 | Ubuntu 22 |
| ALM0 | AlmaLinux |
| POSTGRESQL | PostgreSQL |
| NGINX | Nginx |
| APACHE | Apache HTTP |
| REDIS | Redis |
| ONEUPTIME | OneUptime |
| GITLAB | GitLab |
| GITHUB | GitHub |
| JENKINS | Jenkins |
