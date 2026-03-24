#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List, Set


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def parse_openapi_paths(text: str) -> List[str]:
    lines = text.splitlines()
    in_paths = False
    paths: List[str] = []
    for line in lines:
        if line.strip() == "paths:":
            in_paths = True
            continue
        if in_paths and line.startswith("components:"):
            break
        if in_paths:
            m = re.match(r"^\s{2}(/[^:]+):\s*$", line)
            if m:
                paths.append(m.group(1))
    return sorted(set(paths))


def parse_api_routes(text: str) -> Set[str]:
    routes: Set[str] = set()
    for m in re.finditer(r'path\s*==\s*"([^"]+)"', text):
        routes.add(m.group(1))
    for m in re.finditer(r'path\.startswith\("([^"]+)"\)', text):
        routes.add(m.group(1))
    tuple_pattern = re.compile(r'path\s+in\s+\(([^)]+)\)')
    for m in tuple_pattern.finditer(text):
        block = m.group(1)
        for item in re.findall(r'"([^"]+)"', block):
            routes.add(item)
    return routes


def is_path_implemented(contract_path: str, routes: Set[str]) -> bool:
    if contract_path in routes:
        return True
    if "{" not in contract_path:
        return False
    prefix = contract_path.split("{", 1)[0]
    if prefix.endswith("/") and prefix in routes:
        return True
    for route in routes:
        if route.endswith("/") and route.startswith(prefix):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    openapi_path = root / "docs" / "delivery" / "api" / "openapi.yaml"
    api_path = root / "api" / "minimal_api.py"

    openapi_text = read_text(openapi_path)
    api_text = read_text(api_path)
    contract_paths = parse_openapi_paths(openapi_text)
    impl_routes = parse_api_routes(api_text)

    missing: List[str] = []
    for p in contract_paths:
        if not is_path_implemented(p, impl_routes):
            missing.append(p)

    checks = {
        "has_openapi": bool(openapi_text),
        "has_api_impl": bool(api_text),
        "has_trace_id_field": "trace_id" in openapi_text,
        "has_trace_header": "X-Trace-Id" in openapi_text,
        "path_count": len(contract_paths),
        "missing_paths": missing,
    }
    checks["ok"] = (
        checks["has_openapi"]
        and checks["has_api_impl"]
        and checks["has_trace_id_field"]
        and checks["has_trace_header"]
        and len(missing) == 0
    )
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not checks["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
