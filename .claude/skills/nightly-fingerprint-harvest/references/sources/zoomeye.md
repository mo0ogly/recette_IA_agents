# ZoomEye

## Auth
- Env var: `ZOOMEYE_API_KEY`
- Sign up: https://www.zoomeye.org/profile

## Quotas
- Free: 500 queries/month

## Query syntax
- `app:"nginx"`
- `port:443`
- `country:"FR"`
- `service:"http"`
- `os:"linux"`

## API
- GET `https://api.zoomeye.org/host/search?query=<q>&page=1`
- Header: `API-KEY: <key>`
- Returns `{matches: [{ip, portinfo:{port,banner,headers}}]}`

## Notes
- Focus Asie historically but coverage globale aujourd'hui.
- Banner souvent plus brut que Shodan.
- Pas de body HTTP en standard, juste banner + headers.
