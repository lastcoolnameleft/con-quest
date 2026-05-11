---
title: Con Quest Backlog
description: Outstanding product, engineering, and testing items pending implementation
ms.date: 2026-05-10
ms.topic: how-to
---

## Purpose

This backlog tracks outstanding work items that are not yet complete.

## Active Backlog

### 1. Transport resilience testing for mixed network failure

* Priority: High
* Area: Realtime transport and status UX
* Status: Open
* Goal: Validate behavior when WebSocket fails but normal HTTP requests still succeed

#### Scope

* Simulate WebSocket failure for these paths while leaving HTTP available:
  * /ws/health/
  * /ws/season/{id}/
* Keep these HTTP endpoints reachable:
  * /connection-test/
  * /seasons/{slug}/state/

#### Expected behavior

* Header status indicator leaves green and shows degraded or unavailable
* Manual Test button still succeeds through HTTP
* Season detail page continues working through state polling fallback
* User-facing status remains accurate after reconnect and repeated disconnects

#### Acceptance criteria

* Document a repeatable local test procedure in the QA runbook
* Add automated coverage where feasible for transport state transitions
* Confirm no stale green state after WebSocket disconnect

### 2. Backlog hygiene and triage workflow

* Priority: Medium
* Area: Process
* Status: Open
* Goal: Keep backlog current and actionable

#### Acceptance criteria

* Add owner and target milestone fields for each backlog item
* Review and re-prioritize backlog weekly
* Close or split items that remain vague after triage
