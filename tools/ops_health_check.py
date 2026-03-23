#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_json(url: str, method: str = "GET", body: dict | None = None, headers_extra: dict | None = None) -> tuple[bool, int, dict | str]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if headers_extra:
        headers.update(headers_extra)
    req = Request(url=url, method=method, data=data, headers=headers)
    try:
        with urlopen(req, timeout=8) as resp:
            code = int(resp.status)
            text = resp.read().decode("utf-8", errors="ignore")
            payload = json.loads(text) if text.strip() else {}
            return True, code, payload
    except HTTPError as e:
        return False, int(e.code), str(e)
    except URLError as e:
        return False, 0, str(e)
    except Exception as e:
        return False, 0, str(e)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:18080")
    parser.add_argument("--api-key", type=str, default="dev-key-001")
    parser.add_argument("--readonly-api-key", type=str, default="readonly-key-001")
    parser.add_argument("--disabled-api-key", type=str, default="disabled-key-001")
    parser.add_argument("--revoked-api-key", type=str, default="revoked-key-001")
    parser.add_argument("--rotate-old-api-key", type=str, default="rotate-old-001")
    parser.add_argument("--rotate-new-api-key", type=str, default="rotate-new-001")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    base_url = args.base_url.rstrip("/")
    auth_headers = {"X-API-Key": args.api_key}
    readonly_headers = {"X-API-Key": args.readonly_api_key}
    disabled_headers = {"X-API-Key": args.disabled_api_key}
    revoked_headers = {"X-API-Key": args.revoked_api_key}
    rotate_old_headers = {"X-API-Key": args.rotate_old_api_key}
    rotate_new_headers = {"X-API-Key": args.rotate_new_api_key}
    security = read_json(root / "config" / "security_config.json")
    phase = "dual"
    for g in security.get("rotation_groups", []):
        if str(g.get("old_key", "")).strip() == args.rotate_old_api_key and str(g.get("new_key", "")).strip() == args.rotate_new_api_key:
            phase = str(g.get("phase", "dual")).strip() or "dual"
            break
    old_expected = 200 if phase == "dual" else 401
    new_expected = 200
    search_get_qs = urlencode({"audience": "teacher", "q": "行程", "limit": 1})
    checks = [
        ("health", "GET", f"{base_url}/health", None, None, 200),
        ("topics", "GET", f"{base_url}/topics?audience=teacher&limit=1", None, auth_headers, 200),
        ("problems", "GET", f"{base_url}/problems?audience=student&limit=1", None, auth_headers, 200),
        ("search_get", "GET", f"{base_url}/search?{search_get_qs}", None, auth_headers, 200),
        ("search_post", "POST", f"{base_url}/search", {"audience": "teacher", "q": "行程", "limit": 1}, auth_headers, 200),
        ("graph_validation", "GET", f"{base_url}/graph/validation", None, auth_headers, 200),
        ("quality_summary", "GET", f"{base_url}/quality/summary", None, auth_headers, 200),
        ("auth_whoami", "GET", f"{base_url}/auth/whoami", None, auth_headers, 200),
        ("auth_config", "GET", f"{base_url}/auth/config", None, auth_headers, 200),
        ("auth_reload", "GET", f"{base_url}/auth/reload", None, auth_headers, 200),
        ("auth_rotation", "GET", f"{base_url}/auth/rotation", None, auth_headers, 200),
        ("auth_rotation_check", "GET", f"{base_url}/auth/rotation/check", None, auth_headers, 200),
        ("auth_rotation_advice", "GET", f"{base_url}/auth/rotation/advice", None, auth_headers, 200),
        ("auth_rotation_gate", "GET", f"{base_url}/auth/rotation/gate", None, auth_headers, 200),
        ("auth_rotation_plan", "GET", f"{base_url}/auth/rotation/plan", None, auth_headers, 200),
        ("readonly_whoami", "GET", f"{base_url}/auth/whoami", None, readonly_headers, 200),
        ("readonly_topics", "GET", f"{base_url}/topics?audience=teacher&limit=1", None, readonly_headers, 200),
        ("readonly_forbidden_student_topics", "GET", f"{base_url}/topics?audience=student&limit=1", None, readonly_headers, 401),
        ("readonly_forbidden_graph", "GET", f"{base_url}/graph/validation", None, readonly_headers, 401),
        ("disabled_key_topics", "GET", f"{base_url}/topics?audience=teacher&limit=1", None, disabled_headers, 401),
        ("revoked_key_topics", "GET", f"{base_url}/topics?audience=teacher&limit=1", None, revoked_headers, 401),
        ("rotated_old_key_topics", "GET", f"{base_url}/topics?audience=teacher&limit=1", None, rotate_old_headers, old_expected),
        ("rotated_new_key_topics", "GET", f"{base_url}/topics?audience=teacher&limit=1", None, rotate_new_headers, new_expected),
    ]

    results = []
    for name, method, url, body, headers, expected_status in checks:
        ok, code, payload = fetch_json(url, method=method, body=body, headers_extra=headers)
        results.append(
            {
                "name": name,
                "ok": code == expected_status,
                "status": code,
                "expected_status": expected_status,
                "response": payload,
            }
        )

    failed = [r for r in results if not r["ok"]]
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "total_checks": len(results),
        "failed_checks": len(failed),
        "ok": len(failed) == 0,
        "results": results,
    }

    out_dir = root / "artifacts" / "ops"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "health_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out_dir / "health_history.jsonl").open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "checked_at": report["checked_at"],
                    "ok": report["ok"],
                    "failed_checks": report["failed_checks"],
                    "total_checks": report["total_checks"],
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    lines = [
        "# 运维巡检告警",
        "",
        f"- 检查时间: {report['checked_at']}",
        f"- 检查地址: {base_url}",
        f"- 通过数: {len(results) - len(failed)}/{len(results)}",
        "",
    ]
    if failed:
        lines.append("## 失败项")
        for item in failed:
            lines.append(f"- {item['name']} status={item['status']}")
    else:
        lines.append("## 结果")
        lines.append("- 全部检查通过")
    (out_dir / "alerts.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "failed_checks": len(failed)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
