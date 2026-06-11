# Scheduling

## Recommended cadence

Run once per night, 02:00 Europe/Paris (avoids peak crt.sh load,
respects quota reset cycles).

## systemd timer (recommended on liadev VPS)

`/etc/systemd/system/lia-nightly-harvest.service`:
```ini
[Unit]
Description=LIA-SEC nightly fingerprint harvest
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=liadev
Group=liadev
WorkingDirectory=/opt/lia-sec/dev
EnvironmentFile=-/opt/lia-sec/dev/.claude/skills/nightly-fingerprint-harvest/.env
ExecStart=/usr/bin/python3 /opt/lia-sec/dev/.claude/skills/nightly-fingerprint-harvest/scripts/nightly_run.py --max-rules 30 --max-hosts 3
StandardOutput=append:/var/log/lia-nightly-harvest.log
StandardError=append:/var/log/lia-nightly-harvest.log
```

`/etc/systemd/system/lia-nightly-harvest.timer`:
```ini
[Unit]
Description=Nightly fingerprint harvest timer

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lia-nightly-harvest.timer
```

## Alternative: cron

```cron
0 2 * * *  liadev  bash -lc 'cd /opt/lia-sec/dev && python3 .claude/skills/nightly-fingerprint-harvest/scripts/nightly_run.py --max-rules 30 >> /var/log/lia-nightly-harvest.log 2>&1'
```

## Quota budget per night

With default `--max-rules 30 --max-hosts 3 --sources netlas,crtsh,publicwww,censys,zoomeye`:

| Source | Calls/night | Daily quota | Monthly burn |
|--------|-------------|-------------|--------------|
| netlas | 30 | 50/day | 900 |
| crtsh  | 30 | unlimited | 900 |
| publicwww | 30 | 50/day | 900 |
| censys | 30 | 250/month | ~900 (over budget after 8 days) |
| zoomeye | 30 | 500/month | ~900 (over budget after 16 days) |

For Censys / ZoomEye, throttle by adjusting `--max-rules` per source or
running them on alternate nights. The quota tracker auto-skips when the
monthly cap is reached.

## Manual smoke test

```bash
python3 .claude/skills/nightly-fingerprint-harvest/scripts/nightly_run.py \
    --dry-run --max-rules 3 --sources netlas,crtsh
```

## Env file template (`.env` next to SKILL.md, gitignored)

```env
NETLAS_API_KEY=
CENSYS_API_ID=
CENSYS_API_SECRET=
ZOOMEYE_API_KEY=
RAPID7_SONAR_PATH=/opt/lia-sec/datasets/sonar_https_443.json.gz
```
