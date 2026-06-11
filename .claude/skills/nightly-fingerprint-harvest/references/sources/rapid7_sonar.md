# Rapid7 Open Data Sonar (offline dataset)

## Auth
- None. Datasets are public.

## Quotas
- None (offline). Local CPU and disk bound.

## Download
- Live datasets retired in 2022; historical snapshots remain.
- Source: https://opendata.rapid7.com/sonar.http/
- Archive: https://scans.io/

## Format
- ndjson.gz, one record per line:
  ```json
  {"ip":"1.2.3.4","port":443,"data":"HTTP/1.1 200 OK\\r\\nServer: nginx\\r\\n...","timestamp":1641234567}
  ```

## Env var
- `RAPID7_SONAR_PATH` — absolute path to the local dump (`.json.gz` or `.json`).

## Use case in this skill
- Bulk replay: scan millions of banners for `product`/`vendor` regex.
- Snapshot in time — banners may be stale, version drift possible.
- Best for tier 3 / niche / EOL products that disappeared from live sources.

## Performance hint
- A typical port 443 dump = 50+ GB gzipped.
- Each rule = 1 full pass = expensive. Batch rules with the same
  underlying ndjson and short-circuit on the first N matches.
