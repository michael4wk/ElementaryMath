#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")


def fetch_plan(base_url: str, api_key: str) -> dict:
    req = Request(url=f"{base_url.rstrip('/')}/auth/rotation/plan", method="GET", headers={"X-API-Key": api_key})
    try:
        with urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            if isinstance(payload, dict):
                return payload.get("data", {}) if isinstance(payload.get("data", {}), dict) else {}
    except (HTTPError, URLError, TimeoutError):
        return {}
    except Exception:
        return {}
    return {}


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    parser.add_argument("--group", type=str, default="")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:18080")
    parser.add_argument("--api-key", type=str, default="dev-key-001")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ticket", type=str, default="")
    parser.add_argument("--operator", type=str, default="")
    parser.add_argument("--change-reason", type=str, default="")
    parser.add_argument("--retire-old-action", choices=["disable", "revoke", "keep"], default="disable")
    parser.add_argument("--target-phase", choices=["dual", "cutover", "retire"], default="")
    parser.add_argument("--rollback-enable-old", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    conf_path = root / "config" / "security_config.json"
    conf = read_json(conf_path)
    plan = fetch_plan(args.base_url, args.api_key)
    can_promote = bool(plan.get("can_promote", False))
    blockers = plan.get("blockers", [])
    plans = plan.get("plans", [])
    group_filter = args.group.strip()
    selected = [p for p in plans if (not group_filter or str(p.get("name", "")).strip() == group_filter)]
    if args.target_phase:
        selected = [{**p, "target_phase": args.target_phase} for p in selected]
    actions = [p for p in selected if str(p.get("target_phase", "")) != str(p.get("current_phase", ""))]

    result = {
        "can_promote": can_promote,
        "blockers": blockers,
        "selected_count": len(selected),
        "change_count": len(actions),
        "changed": [],
        "retire_actions": [],
        "rollback_actions": [],
        "applied": False,
    }

    if not args.apply:
        print(json.dumps(result, ensure_ascii=False))
        return

    ticket = args.ticket.strip()
    operator = args.operator.strip()
    change_reason = args.change_reason.strip()
    if not ticket:
        print(json.dumps({**result, "error": "missing --ticket for apply mode"}, ensure_ascii=False))
        raise SystemExit(2)
    if not operator:
        print(json.dumps({**result, "error": "missing --operator for apply mode"}, ensure_ascii=False))
        raise SystemExit(2)

    if not can_promote and not args.force:
        print(json.dumps({**result, "error": "gate blocked, use --force to override"}, ensure_ascii=False))
        raise SystemExit(2)

    groups = conf.get("rotation_groups", [])
    target_by_name = {str(x.get("name", "")).strip(): str(x.get("target_phase", "")).strip() for x in actions}
    api_key_rows = conf.get("api_keys", [])
    api_key_map = {}
    for row in api_key_rows:
        if isinstance(row, dict):
            key = str(row.get("key", "")).strip()
            if key:
                api_key_map[key] = row
    revoked_rows = conf.get("revoked_keys", [])
    changed = []
    retire_actions = []
    rollback_actions = []
    for g in groups:
        name = str(g.get("name", "")).strip()
        target = target_by_name.get(name, "")
        if not target:
            continue
        current = str(g.get("phase", "")).strip()
        if target != current:
            g["phase"] = target
            changed.append({"name": name, "from": current, "to": target})
            old_key = str(g.get("old_key", "")).strip()
            if target == "retire":
                if old_key and args.retire_old_action == "disable":
                    row = api_key_map.get(old_key)
                    if row is not None:
                        row["enabled"] = False
                        retire_actions.append({"name": name, "old_key": old_key, "action": "disabled"})
                elif old_key and args.retire_old_action == "revoke":
                    exists = False
                    for r in revoked_rows:
                        if isinstance(r, str) and r.strip() == old_key:
                            exists = True
                            break
                        if isinstance(r, dict) and str(r.get("key", "")).strip() == old_key:
                            exists = True
                            break
                    if not exists:
                        revoked_rows.append({"key": old_key, "reason": "rotation_retire"})
                    retire_actions.append({"name": name, "old_key": old_key, "action": "revoked"})
                elif old_key and args.retire_old_action == "keep":
                    retire_actions.append({"name": name, "old_key": old_key, "action": "kept"})
            elif target in ("dual", "cutover") and args.rollback_enable_old:
                if old_key:
                    row = api_key_map.get(old_key)
                    if row is not None and not bool(row.get("enabled", True)):
                        row["enabled"] = True
                        rollback_actions.append({"name": name, "old_key": old_key, "action": "enabled"})
    conf["rotation_groups"] = groups
    conf["api_keys"] = api_key_rows
    conf["revoked_keys"] = revoked_rows
    write_json(conf_path, conf)
    action_row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "can_promote": can_promote,
        "force": bool(args.force),
        "group_filter": group_filter,
        "target_phase": args.target_phase,
        "ticket": ticket,
        "operator": operator,
        "change_reason": change_reason,
        "retire_old_action": args.retire_old_action,
        "rollback_enable_old": bool(args.rollback_enable_old),
        "changed": changed,
        "retire_actions": retire_actions,
        "rollback_actions": rollback_actions,
    }
    append_jsonl(root / "artifacts" / "ops" / "rotation_actions.jsonl", action_row)
    print(
        json.dumps(
            {**result, "changed": changed, "retire_actions": retire_actions, "rollback_actions": rollback_actions, "applied": True},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
