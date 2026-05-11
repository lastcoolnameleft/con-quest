---
title: Con Quest MVP Build Plan
description: Phased implementation plan for Con Quest including architecture, data model, realtime reliability, security, and verification.
date: 2026-05-10
topic: how-to
---

## Plan: Con Quest MVP Build Plan

Build a greenfield, mobile-first Django app for convention quest gameplay with progressive identity, reusable quests, dual quest modes (scheduled/open), near-real-time scheduled starts, multi-media blob-backed submissions, moderation, and 0-5 scoring. Recommended approach is phased delivery: establish foundations and data model first, then implement gameplay flows, then reliability, then moderation/security, then verification hardening.

**Steps**
1. Phase 1 - Foundation and Project Bootstrap
1. Confirm runtime/dependency baseline and lock to Django 6 by default with compatibility fallback to Django 5.2 LTS if blocked.
2. Scaffold project, apps, settings split, env config, ASGI entrypoint, Docker compose, and Redis service.
3. Configure SQLite for MVP and structured settings for future DB swap.
4. Configure static files, PWA shell assets, and HTMX/Bootstrap baseline layout.
5. Define environment contract for blob storage, signed upload/read URLs, and media security policies.

2. Phase 2 - Core Domain Model and Migrations (*depends on Phase 1*)
1. Implement Account, Season, SeasonParticipant.
2. Implement reusable quest split: Quest + SeasonQuest.
3. Implement QuestAssignment and Submission with integer score constraint 0..5.
4. Implement SubmissionMedia one-to-many with ordered media and per-file metadata.
5. Implement ModerationReport and append-only AuditLog.
6. Add DB constraints/indexes:
- unique participant handle per season
- unique participant per season account mapping (non-null account)
- unique seasonquest+participant assignment
- unique submissionmedia sort order per submission
- score bounds and required reason on score edits (app-level + model validation)

3. Phase 3 - Identity and Join Flows (*depends on Phase 2*)
1. Guest-first join flow: QR/code entry + unique handle + season participant session.
2. Optional social sign-in integration and guest-claim flow with safe merge handling.
3. Implement private-by-default season visibility and tokenized entry gating.
4. Add role/permission enforcement for Host, Player, Viewer, Admin.

4. Phase 4 - Quest Authoring and Assignment (*depends on Phases 2-3*)
1. Host CRUD for Quest and SeasonQuest with quest reuse across seasons.
3. Configure per-seasonquest mode fields:
- quest_mode scheduled/open
- assignment_policy host_assigned/open_claim
- start_mode admin_triggered for scheduled
3. Implement assignment creation paths:
- host-assigned issuance
- open claim on start
- QR/code sourced assignment tagging

5. Phase 5 - Submission and Scoring Flows (*depends on Phases 3-4*)
1. Build mobile-first quest run flow and one-submission-per-assignment handling.
2. Implement multi-media upload workflow with blob-backed persistence and SubmissionMedia rows.
3. Enforce server-authoritative validation:
- video duration <= 15 seconds
- image file size <= 30 MB
- video file size <= 100 MB
- allowed mime/extension set
- mismatch rejection
4. Enforce scoring workflow with integer 0-5, pending state for unscored, and score edit reason requirements.
5. Compute leaderboard from scored submissions only; apply tie-breakers in deterministic order.

6. Phase 6 - Scheduled vs Open Quest Runtime (*depends on Phases 4-5*)
1. Scheduled runtime states: waiting -> live -> closed.
2. Admin-triggered start endpoint sets canonical started_at/ends_at from duration.
3. Open runtime enables scan-and-go and live event progression.
4. Respect reveal policy variants (instant/end_of_quest/end_of_season).

7. Phase 7 - Real-Time Fairness and Connection Reliability (*depends on Phase 6*)
1. Implement Django Channels consumers and Redis channel layer for scheduled start broadcast.
2. Add client transport strategy:
- websocket primary
- short polling fallback
- transport status indicator (live/degraded/offline)
3. Implement server-time synchronization strategy and optional fairness buffer.
4. Ensure backend rejects early/late submissions based on server timestamps only.
5. Build Test Connection preflight (reachability, latency, websocket, clock offset) with Ready/Risky/Not Ready outcomes and guidance.

8. Phase 8 - Security, Moderation, and Ops Controls (*parallel with late Phase 7 where possible*)
1. Rate limiting rules per endpoint group (join/auth/submission/upload/report).
2. Moderation report intake and host/admin resolution actions.
3. Audit logging for scoring and moderation mutations (append-only semantics).
4. Media access hardening using short-lived signed read URLs for private content.
5. EXIF stripping for image uploads.

9. Phase 9 - Verification and Hardening (*depends on all prior phases*)
1. Automated tests:
- model constraints
- permissions
- join/claim flows
- assignment/submission/scoring flows
- scheduled start synchronization behavior
- fallback transport behavior
- moderation and audit logging
- media validation checks
2. Manual QA scripts:
- low-bandwidth convention simulation
- concurrent scheduled start fairness checks
- blob upload/read expiration checks
3. Performance checks for high join/submit bursts.
4. Deployment sanity check via Docker compose runbook.

## Phase 9 Artifacts

* Manual QA runbook: [docs/manual-qa-runbook.md](docs/manual-qa-runbook.md)
* Deployment sanity runbook: [docs/deployment-sanity-runbook.md](docs/deployment-sanity-runbook.md)
* Burst rate-limit probe script: [scripts/burst-checks.sh](scripts/burst-checks.sh)
* Executed verification evidence: [docs/phase9-execution-log.md](docs/phase9-execution-log.md)

**Relevant files**
- /Users/thfalgou/git/lastcoolnameleft/con-quest/manage.py — Django entrypoint bootstrap.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/con_quest/settings.py — environment, apps, channels, storage, security settings.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/con_quest/asgi.py — ASGI + websocket routing integration.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/con_quest/urls.py — HTTP routing and role-protected endpoints.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/apps/accounts/ — Account + optional social auth + claim workflows.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/apps/seasons/ — Season + SeasonParticipant models and join gating.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/apps/quests/ — Quest + SeasonQuest + QuestAssignment domain logic.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/apps/submissions/ — Submission + SubmissionMedia + validation.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/apps/leaderboard/ — scoring aggregation and tie-break resolution.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/apps/realtime/ — channels consumers/events for scheduled starts.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/apps/moderation/ — ModerationReport + admin workflows.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/apps/audit/ — append-only AuditLog and write helpers.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/templates/ — mobile-first HTMX templates and fallback UX.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/static/ — PWA manifest/service worker and client transport checks.
- /Users/thfalgou/git/lastcoolnameleft/con-quest/docker-compose.yml — app + redis (+ optional worker) orchestration.

**Verification**
1. Run full test suite locally with sqlite and deterministic time fixtures.
2. Execute scheduled-quest fairness test with N clients receiving admin-trigger start; verify server-authoritative submission windows.
3. Validate open-quest scan-and-go throughput using burst simulation for join and submit endpoints.
4. Verify media rules with matrix tests (duration, size, mime mismatch, multi-file ordering).
5. Verify role/permission matrix for host/player/viewer/admin.
6. Verify guest-to-account claim preserves season history and prevents duplicate season participant mapping.
7. Verify signed blob read URL expiry and private content access restrictions.
8. Validate readiness preflight states by simulating websocket failure and high latency.

**Decisions**
- Keep guest-first participation with optional social sign-in claim.
- Support both quest modes: scheduled and open.
- Scheduled starts are admin-triggered and near-real-time with websocket + fallback polling.
- Reuse quests across seasons via Quest + SeasonQuest split.
- Support multiple media per submission via SubmissionMedia table.
- Use Azure Blob Storage for all media; store only metadata/references in DB.
- Enforce media limits: images up to 30 MB, videos up to 100 MB, and max 15s video duration.
- Open-quest live leaderboard uses websocket primary transport with polling fallback.
- Fixed score scale is integer 0-5.

**Further Considerations**
1. Decide whether oversized-but-short video auto-transcode is in MVP or deferred (current plan: allow up to 100 MB without transcode).
2. Confirm websocket scaling targets for open-quest leaderboard traffic at expected convention peak load.

## Closeout Status

* Implementation scope: complete.
* Automated verification scope: complete.
* Deployment sanity runbook: executed and passing (see [docs/phase9-execution-log.md](docs/phase9-execution-log.md)).
* Remaining manual-only sign-off checks:
* Browser low-bandwidth UX pass under network throttling.
* Signed media URL expiry behavior with real-time wait validation.