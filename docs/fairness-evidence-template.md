---
title: Con Quest Fairness Evidence Template
description: Fill-in template for multi-client scheduled fairness evidence capture
date: 2026-05-10
topic: how-to
---

## Run metadata

* Date:
* Environment:
* Operator:
* Season slug:
* Scheduled quest id:
* Base URL:

## Automation command

```bash
python3 scripts/fairness-capture.py <season-slug> <quest-id> --base-url <base-url>
```

## Captured output

Paste command output here.

```text

```

## Validation checklist

* `started_at_match: True`
* `ends_at_match: True`
* Both clients report quest status `live` during the active window
* No server 5xx responses during capture

## Notes

* Observed client receive jitter:
* Any anomalies:
* Follow-up action:
