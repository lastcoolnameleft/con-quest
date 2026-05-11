#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class QuestWindow:
    started_at: str | None
    ends_at: str | None
    status: str | None


def fetch_quest_window(base_url: str, slug: str, quest_id: int, forwarded_for: str) -> QuestWindow:
    url = f"{base_url.rstrip('/')}/seasons/{slug}/state/"
    req = urllib.request.Request(url, headers={"X-Forwarded-For": forwarded_for})
    with urllib.request.urlopen(req, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))

    for quest in payload.get("quests", []):
        if quest.get("id") == quest_id:
            return QuestWindow(
                started_at=quest.get("started_at"),
                ends_at=quest.get("ends_at"),
                status=quest.get("status"),
            )

    raise RuntimeError(f"Quest id {quest_id} not found in state payload")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture scheduled quest timing from two client identities.")
    parser.add_argument("slug", help="Season slug, for example qa-season")
    parser.add_argument("quest_id", type=int, help="SeasonQuest id to inspect")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL for the running app")
    parser.add_argument("--client-a", default="10.10.10.1", help="X-Forwarded-For value for first client")
    parser.add_argument("--client-b", default="10.10.10.2", help="X-Forwarded-For value for second client")
    parser.add_argument("--wait-seconds", type=int, default=20, help="How long to wait for started_at to appear")
    args = parser.parse_args()

    deadline = time.time() + args.wait_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            window_a = fetch_quest_window(args.base_url, args.slug, args.quest_id, args.client_a)
            window_b = fetch_quest_window(args.base_url, args.slug, args.quest_id, args.client_b)
            if window_a.started_at and window_b.started_at:
                break
            time.sleep(1)
        except (urllib.error.URLError, RuntimeError) as exc:
            last_error = exc
            time.sleep(1)
    else:
        if last_error:
            print(f"ERROR: {last_error}")
        print("ERROR: Timed out waiting for quest start window")
        return 1

    started_match = window_a.started_at == window_b.started_at
    ends_match = window_a.ends_at == window_b.ends_at

    print("Fairness capture")
    print(f"quest_id: {args.quest_id}")
    print(f"client_a: {args.client_a}")
    print(f"client_b: {args.client_b}")
    print(f"client_a_status: {window_a.status}")
    print(f"client_b_status: {window_b.status}")
    print(f"client_a_started_at: {window_a.started_at}")
    print(f"client_b_started_at: {window_b.started_at}")
    print(f"client_a_ends_at: {window_a.ends_at}")
    print(f"client_b_ends_at: {window_b.ends_at}")
    print(f"started_at_match: {started_match}")
    print(f"ends_at_match: {ends_match}")

    return 0 if started_match and ends_match else 2


if __name__ == "__main__":
    raise SystemExit(main())
