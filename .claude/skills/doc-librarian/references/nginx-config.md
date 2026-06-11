# Nginx Configuration -- liascan.tech/docs/

## Location Block

Add this block to `/etc/nginx/sites-available/liascan.tech` **BEFORE** the React SPA catch-all:

```nginx
# Documentation site -- MUST be before the React SPA catch-all location /
location /docs/ {
    alias /opt/lia-sec/source/docs-site/;
    try_files $uri $uri/ $uri.html =404;
    
    # Cache static assets
    location ~* \.(js|css|png|svg|ico|woff2|ttf)$ {
        alias /opt/lia-sec/source/docs-site/;
        try_files $uri =404;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
    
    # Disable caching for Pagefind index (updated on each build)
    location /docs/pagefind/ {
        alias /opt/lia-sec/source/docs-site/pagefind/;
        try_files $uri =404;
        expires -1;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }
}

# React SPA catch-all (existing -- keep AFTER /docs/)
location / {
    root /opt/lia-sec/source/sigma-react-frontend/build;
    try_files $uri $uri/ /index.html;
}
```

## Apply and Verify

```bash
# Test config before applying
sudo nginx -t

# Apply
sudo systemctl reload nginx

# Verify /docs/ is served
curl -s -o /dev/null -w "%{http_code}" https://liascan.tech/docs/
# Expected: 200

# Verify React app still works
curl -s -o /dev/null -w "%{http_code}" https://liascan.tech/
# Expected: 200

# Verify Pagefind search
curl -s -o /dev/null -w "%{http_code}" https://liascan.tech/docs/pagefind/pagefind.js
# Expected: 200
```

## Why /docs/ Path (Not Subdomain)

- `docs.liascan.tech` blocked by HSTS `includeSubDomains` directive (no wildcard cert)
- `/docs/` path avoids SSL reconfiguration, no extra DNS entry
- `location /docs/` must appear BEFORE `location /` in nginx config (nginx longest prefix match)
- `alias` directive (not `root`) required because the path differs from document root

## Rollback Procedure

```bash
# Remove the /docs/ location block from nginx config
sudo nano /etc/nginx/sites-available/liascan.tech
# Delete the location /docs/ block

# Test and reload
sudo nginx -t && sudo systemctl reload nginx

# Verify React app still works
curl https://liascan.tech/
```

## Docs Site Layout on VPS

```
/opt/lia-sec/source/docs-site/         <- Nginx alias target
├── index.html                          <- Docusaurus SPA entry
├── assets/                             <- CSS, JS, fonts
├── pagefind/                           <- Full-text search index
│   ├── pagefind.js
│   └── pagefind-*.pf_meta
└── docs/                               <- Doc pages by category
    ├── api/
    ├── architecture/
    ├── technical/
    ├── user-guides/
    ├── security/
    └── specs/
```

## Deploy Command

```bash
# From /opt/lia-sec/dev/ (already on VPS)
rsync -avz --delete docs-site/build/ /opt/lia-sec/source/docs-site/
sudo systemctl reload nginx
```

Or via `deploy.sh` if extended to support docs (future enhancement).
