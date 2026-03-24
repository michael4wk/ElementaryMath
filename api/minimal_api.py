#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import parse_qs, urlparse
import uuid


def read_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class AppState:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.serving_dir = project_root / "artifacts" / "serving"
        self.cache: Dict[str, List[dict]] = {}
        self.reload()

    def reload(self) -> None:
        for audience in ("teacher", "student"):
            self.cache[f"topics_{audience}"] = read_jsonl(self.serving_dir / f"topics_{audience}.jsonl")
            self.cache[f"problems_{audience}"] = read_jsonl(self.serving_dir / f"problems_{audience}.jsonl")
            self.cache[f"explanations_{audience}"] = read_jsonl(self.serving_dir / f"explanations_{audience}.jsonl")
        graph_rows = read_jsonl(self.project_root / "artifacts" / "graph" / "topic_graph.jsonl")
        chapter_rows = read_jsonl(self.project_root / "artifacts" / "graph" / "chapter_graph.jsonl")
        self.cache["graph_map"] = {r.get("topic_id"): r for r in graph_rows if r.get("topic_id")}
        self.cache["chapter_graph_map"] = {r.get("chapter_id"): r for r in chapter_rows if r.get("chapter_id")}
        self.cache["quality_report"] = read_json(self.project_root / "artifacts" / "quality" / "report.json")
        self.cache["validation_report"] = read_json(self.project_root / "artifacts" / "quality" / "validation.json")
        self.cache["quality_gate_report"] = read_json(self.project_root / "artifacts" / "quality" / "gate_report.json")
        self.cache["quality_gate_profiles"] = read_json(self.project_root / "config" / "quality_gate_profiles.json")
        self.cache["graph_validation"] = read_json(self.project_root / "artifacts" / "graph" / "validation.json")
        security_path = self.project_root / "config" / "security_config.json"
        security = read_json(security_path)
        self.cache["auth_enabled"] = bool(security.get("auth_enabled", False))
        key_rules: Dict[str, dict] = {}
        for item in security.get("api_keys", []):
            if isinstance(item, str):
                key = item.strip()
                if key:
                    key_rules[key] = {
                        "name": self._safe_name_from_key(key),
                        "enabled": True,
                        "not_before": "",
                        "not_after": "",
                        "allow_all": True,
                        "allow_prefixes": [],
                        "allow_audiences": [],
                    }
                continue
            if isinstance(item, dict):
                key = str(item.get("key", "")).strip()
                if not key:
                    continue
                prefixes = [str(x).strip() for x in item.get("allow_prefixes", []) if str(x).strip()]
                allow_audiences = [str(x).strip() for x in item.get("allow_audiences", []) if str(x).strip()]
                allow_all = bool(item.get("allow_all", False) or not prefixes)
                key_rules[key] = {
                    "name": str(item.get("name", "")).strip() or self._safe_name_from_key(key),
                    "enabled": bool(item.get("enabled", True)),
                    "not_before": str(item.get("not_before", "")).strip(),
                    "not_after": str(item.get("not_after", "")).strip(),
                    "allow_all": allow_all,
                    "allow_prefixes": prefixes,
                    "allow_audiences": allow_audiences,
                }
        self.cache["api_key_rules"] = key_rules
        self.cache["public_paths"] = {str(x).strip() for x in security.get("public_paths", []) if str(x).strip()}
        rotation_groups: List[dict] = []
        rotation_map: Dict[str, dict] = {}
        for item in security.get("rotation_groups", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            old_key = str(item.get("old_key", "")).strip()
            new_key = str(item.get("new_key", "")).strip()
            phase = str(item.get("phase", "dual")).strip() or "dual"
            if not old_key or not new_key:
                continue
            if phase not in ("dual", "cutover", "retire"):
                phase = "dual"
            group = {"name": name or f"{self._safe_name_from_key(old_key)}->{self._safe_name_from_key(new_key)}", "old_key": old_key, "new_key": new_key, "phase": phase}
            rotation_groups.append(group)
            rotation_map[old_key] = group
            rotation_map[new_key] = group
        self.cache["rotation_groups"] = rotation_groups
        self.cache["rotation_map"] = rotation_map
        gate = security.get("rotation_gate", {})
        self.cache["rotation_gate"] = {
            "min_consecutive_ok": int(gate.get("min_consecutive_ok", 2) or 2),
            "require_rotation_check_ok": bool(gate.get("require_rotation_check_ok", True)),
        }
        cors = security.get("cors", {}) if isinstance(security.get("cors", {}), dict) else {}
        allow_origins = [str(x).strip() for x in cors.get("allow_origins", []) if str(x).strip()]
        if not allow_origins:
            allow_origins = ["*"]
        allow_methods = [str(x).strip().upper() for x in cors.get("allow_methods", []) if str(x).strip()]
        if not allow_methods:
            allow_methods = ["GET", "POST", "OPTIONS"]
        allow_headers = [str(x).strip() for x in cors.get("allow_headers", []) if str(x).strip()]
        if not allow_headers:
            allow_headers = ["Content-Type", "X-API-Key", "X-Trace-Id"]
        expose_headers = [str(x).strip() for x in cors.get("expose_headers", []) if str(x).strip()]
        if not expose_headers:
            expose_headers = ["X-Trace-Id"]
        self.cache["cors"] = {
            "enabled": bool(cors.get("enabled", True)),
            "allow_origins": allow_origins,
            "allow_methods": allow_methods,
            "allow_headers": allow_headers,
            "expose_headers": expose_headers,
            "allow_credentials": bool(cors.get("allow_credentials", False)),
            "max_age": int(cors.get("max_age", 600) or 600),
        }
        revoked_map: Dict[str, str] = {}
        for item in security.get("revoked_keys", []):
            if isinstance(item, str):
                key = item.strip()
                if key:
                    revoked_map[key] = "revoked"
                continue
            if isinstance(item, dict):
                key = str(item.get("key", "")).strip()
                if key:
                    revoked_map[key] = str(item.get("reason", "revoked")).strip() or "revoked"
        self.cache["revoked_keys"] = revoked_map
        self.cache["security_config_path"] = str(security_path.resolve())
        self.cache["security_config_mtime"] = int(security_path.stat().st_mtime_ns) if security_path.exists() else 0
        ops_dir = self.project_root / "artifacts" / "ops"
        ops_dir.mkdir(parents=True, exist_ok=True)
        self.cache["access_log_path"] = str((ops_dir / "access.log").resolve())
        self.cache["health_history_path"] = str((ops_dir / "health_history.jsonl").resolve())

    def _safe_name_from_key(self, key: str) -> str:
        return f"key-{key[:6]}"


class Handler(BaseHTTPRequestHandler):
    state: AppState

    def _new_trace(self) -> str:
        trace_id = self.headers.get("X-Trace-Id", "").strip()
        if trace_id:
            return trace_id[:128]
        return uuid.uuid4().hex

    def _ensure_trace(self) -> str:
        if not hasattr(self, "_trace_id") or not self._trace_id:
            self._trace_id = self._new_trace()
        return self._trace_id

    def _log_access(self, code: int) -> None:
        path = self.path
        method = self.command
        trace_id = self._ensure_trace()
        now = datetime.now(timezone.utc).isoformat()
        auth = getattr(self, "_auth_context", {})
        line = json.dumps(
            {
                "ts": now,
                "trace_id": trace_id,
                "method": method,
                "path": path,
                "status": code,
                "auth_enabled": bool(self.state.cache.get("auth_enabled", False)),
                "authorized": auth.get("authorized", False),
                "auth_reason": auth.get("reason", ""),
                "api_key_id": auth.get("api_key_id", ""),
                "api_key_name": auth.get("api_key_name", ""),
                "audience_hint": auth.get("audience_hint", ""),
                "revoked_reason": auth.get("revoked_reason", ""),
            },
            ensure_ascii=False,
        )
        log_path = Path(str(self.state.cache.get("access_log_path", "")))
        if str(log_path):
            with log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _bad_request(self, message: str) -> None:
        self._json(400, {"code": 400, "message": message, "data": None})

    def _unauthorized(self, message: str = "unauthorized") -> None:
        self._json(401, {"code": 401, "message": message, "data": None})

    def _key_id(self, key: str) -> str:
        if not key:
            return ""
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
        return f"key_{digest}"

    def _maybe_reload_auth_config(self) -> None:
        path = Path(str(self.state.cache.get("security_config_path", "")))
        if not str(path) or not path.exists():
            return
        current = int(path.stat().st_mtime_ns)
        last = int(self.state.cache.get("security_config_mtime", 0))
        if current != last:
            self.state.reload()

    def _authorize(self, path: str, audience_hint: str = "") -> tuple[bool, dict]:
        self._maybe_reload_auth_config()
        ctx = {
            "authorized": False,
            "reason": "",
            "api_key_id": "",
            "api_key_name": "",
            "allow_all": False,
            "allow_prefixes": [],
            "allow_audiences": [],
            "audience_hint": audience_hint,
            "revoked_reason": "",
            "rotation_group": "",
            "rotation_phase": "",
        }
        auth_enabled = bool(self.state.cache.get("auth_enabled", False))
        if not auth_enabled:
            ctx.update({"authorized": True, "reason": "auth_disabled"})
            return True, ctx
        public_paths = self.state.cache.get("public_paths", set())
        if path in public_paths:
            ctx.update({"authorized": True, "reason": "public_path"})
            return True, ctx
        api_key = self.headers.get("X-API-Key", "").strip()
        if not api_key:
            ctx.update({"reason": "missing_key"})
            return False, ctx
        key_rules = self.state.cache.get("api_key_rules", {})
        rule = key_rules.get(api_key)
        if not rule:
            ctx.update({"reason": "invalid_key", "api_key_id": self._key_id(api_key)})
            return False, ctx
        ctx["api_key_id"] = self._key_id(api_key)
        ctx["api_key_name"] = str(rule.get("name", "")).strip()
        rotation_map = self.state.cache.get("rotation_map", {})
        rotate = rotation_map.get(api_key)
        if rotate:
            ctx["rotation_group"] = str(rotate.get("name", "")).strip()
            ctx["rotation_phase"] = str(rotate.get("phase", "")).strip()
            phase = str(rotate.get("phase", "")).strip()
            is_old = api_key == str(rotate.get("old_key", "")).strip()
            if phase == "cutover" and is_old:
                ctx.update({"reason": "key_rotated_out"})
                return False, ctx
            if phase == "retire" and is_old:
                ctx.update({"reason": "key_retired"})
                return False, ctx
        revoked_map = self.state.cache.get("revoked_keys", {})
        revoked_reason = str(revoked_map.get(api_key, "")).strip()
        if revoked_reason:
            ctx.update({"reason": "key_revoked", "revoked_reason": revoked_reason})
            return False, ctx
        if not bool(rule.get("enabled", True)):
            ctx.update({"reason": "key_disabled"})
            return False, ctx
        now = datetime.now(timezone.utc)
        not_before = str(rule.get("not_before", "")).strip()
        if not_before:
            try:
                nb = datetime.fromisoformat(not_before.replace("Z", "+00:00"))
                if nb.tzinfo is None:
                    nb = nb.replace(tzinfo=timezone.utc)
                if now < nb:
                    ctx.update({"reason": "key_not_active"})
                    return False, ctx
            except Exception:
                ctx.update({"reason": "key_invalid_window"})
                return False, ctx
        not_after = str(rule.get("not_after", "")).strip()
        if not_after:
            try:
                na = datetime.fromisoformat(not_after.replace("Z", "+00:00"))
                if na.tzinfo is None:
                    na = na.replace(tzinfo=timezone.utc)
                if now > na:
                    ctx.update({"reason": "key_expired"})
                    return False, ctx
            except Exception:
                ctx.update({"reason": "key_invalid_window"})
                return False, ctx
        ctx["allow_all"] = bool(rule.get("allow_all", False))
        ctx["allow_prefixes"] = list(rule.get("allow_prefixes", []))
        ctx["allow_audiences"] = list(rule.get("allow_audiences", []))
        if ctx["allow_audiences"]:
            audience_sensitive = path == "/search" or path.startswith("/topics") or path.startswith("/problems")
            if audience_sensitive:
                if not audience_hint:
                    ctx.update({"reason": "audience_missing"})
                    return False, ctx
                if audience_hint not in ctx["allow_audiences"]:
                    ctx.update({"reason": "audience_denied"})
                    return False, ctx
        if rule.get("allow_all", False):
            ctx.update({"authorized": True, "reason": "allow_all"})
            return True, ctx
        prefixes = rule.get("allow_prefixes", [])
        ok = any(path.startswith(prefix) for prefix in prefixes)
        ctx.update({"authorized": ok, "reason": "prefix_allowed" if ok else "prefix_denied"})
        return ok, ctx

    def _get_text_param(self, qs: dict, key: str, default: str = "") -> str:
        return qs.get(key, [default])[0].strip()

    def _get_int_param(self, qs: dict, key: str, default: int, min_value: int = 0, max_value: int = 500) -> Tuple[int, str]:
        raw = self._get_text_param(qs, key, str(default))
        try:
            value = int(raw)
        except ValueError:
            return default, f"invalid {key}"
        if value < min_value or value > max_value:
            return default, f"{key} out of range [{min_value},{max_value}]"
        return value, ""

    def _get_bool_param(self, qs: dict, key: str) -> Tuple[bool | None, str]:
        raw = self._get_text_param(qs, key, "")
        if raw == "":
            return None, ""
        val = raw.lower()
        if val in ("1", "true", "yes", "y"):
            return True, ""
        if val in ("0", "false", "no", "n"):
            return False, ""
        return None, f"invalid {key}"

    def _contains(self, row: dict, q: str) -> bool:
        ql = q.lower()
        for key in ("topic_id", "title", "stem", "difficulty", "grade_band"):
            val = row.get(key)
            if isinstance(val, str) and ql in val.lower():
                return True
        for key in ("method_tags", "learning_objectives", "common_mistakes"):
            val = row.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and ql in item.lower():
                        return True
        return False

    def _write_cors_headers(self) -> None:
        cors = self.state.cache.get("cors", {})
        if not bool(cors.get("enabled", False)):
            return
        allow_origins = cors.get("allow_origins", ["*"])
        allow_credentials = bool(cors.get("allow_credentials", False))
        req_origin = self.headers.get("Origin", "").strip()
        origin_header = "*"
        origin_allowed = False
        if "*" in allow_origins:
            origin_header = req_origin if allow_credentials and req_origin else "*"
            origin_allowed = True
        elif req_origin and req_origin in allow_origins:
            origin_header = req_origin
            origin_allowed = True
        elif not req_origin and allow_origins:
            origin_header = allow_origins[0]
            origin_allowed = True
        else:
            origin_header = "null"
        self.send_header("Access-Control-Allow-Origin", origin_header)
        if req_origin:
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", ",".join(cors.get("allow_methods", ["GET", "POST", "OPTIONS"])))
        self.send_header("Access-Control-Allow-Headers", ",".join(cors.get("allow_headers", ["Content-Type", "X-API-Key", "X-Trace-Id"])))
        self.send_header("Access-Control-Expose-Headers", ",".join(cors.get("expose_headers", ["X-Trace-Id"])))
        self.send_header("Access-Control-Max-Age", str(int(cors.get("max_age", 600) or 600)))
        if allow_credentials and origin_allowed and origin_header != "*":
            self.send_header("Access-Control-Allow-Credentials", "true")

    def _json(self, code: int, data: dict) -> None:
        trace_id = self._ensure_trace()
        if isinstance(data, dict) and "trace_id" not in data:
            data = {**data, "trace_id": trace_id}
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._write_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Trace-Id", trace_id)
        self.end_headers()
        self.wfile.write(body)
        self._log_access(code)

    def do_OPTIONS(self) -> None:
        self._trace_id = self._new_trace()
        self._auth_context = {"authorized": True, "reason": "cors_preflight"}
        self.send_response(204)
        self._write_cors_headers()
        self.send_header("Content-Length", "0")
        self.send_header("X-Trace-Id", self._ensure_trace())
        self.end_headers()
        self._log_access(204)

    def _topic_problem_stats(self, audience: str, topic_id: str) -> dict:
        rows = [r for r in self.state.cache[f"problems_{audience}"] if r.get("topic_id") == topic_id]
        return {
            "problem_count": len(rows),
            "with_answer_count": sum(1 for r in rows if (r.get("answer") or "").strip()),
            "with_analysis_count": sum(1 for r in rows if r.get("analysis_steps")),
            "grade_band_distribution": self._distribution(rows, "grade_band"),
            "difficulty_distribution": self._distribution(rows, "difficulty"),
        }

    def _distribution(self, rows: List[dict], key: str) -> dict:
        out: Dict[str, int] = {}
        for row in rows:
            val = str(row.get(key, "")).strip()
            if not val:
                continue
            out[val] = out.get(val, 0) + 1
        return out

    def _sort_rows(self, rows: List[dict], order_by: str, order: str) -> List[dict]:
        reverse = order == "desc"
        key = order_by.strip() or "topic_id"
        return sorted(rows, key=lambda r: str(r.get(key, "")).strip(), reverse=reverse)

    def _filter_topics(
        self,
        rows: List[dict],
        audience: str,
        q: str,
        chapter_id: str,
        domain: str,
        grade_band: str,
        difficulty: str,
        has_pre: bool | None,
        has_obj: bool | None,
    ) -> List[dict]:
        out = rows
        if q:
            out = [r for r in out if self._contains(r, q)]
        if chapter_id:
            out = [r for r in out if r.get("topic_id", "").startswith(f"{chapter_id}-")]
        if domain:
            d = domain[:-1] if domain.endswith("-") else domain
            out = [r for r in out if str(r.get("topic_id", "")).startswith(f"{d}-")]
        if grade_band or difficulty:
            problem_rows = self.state.cache.get(f"problems_{audience}", [])
            if grade_band:
                problem_rows = [r for r in problem_rows if str(r.get("grade_band", "")).strip() == grade_band]
            if difficulty:
                problem_rows = [r for r in problem_rows if str(r.get("difficulty", "")).strip() == difficulty]
            topic_ids = {str(r.get("topic_id", "")).strip() for r in problem_rows if str(r.get("topic_id", "")).strip()}
            out = [r for r in out if str(r.get("topic_id", "")).strip() in topic_ids]
        if has_pre is not None:
            if has_pre:
                out = [r for r in out if self.state.cache.get("graph_map", {}).get(r.get("topic_id", ""), {}).get("prerequisites")]
            else:
                out = [r for r in out if not self.state.cache.get("graph_map", {}).get(r.get("topic_id", ""), {}).get("prerequisites")]
        if has_obj is not None:
            if has_obj:
                out = [r for r in out if r.get("learning_objectives")]
            else:
                out = [r for r in out if not r.get("learning_objectives")]
        return out

    def _filter_problems(
        self, rows: List[dict], topic_id: str, chapter_id: str, grade_band: str, difficulty: str, method_tag: str, q: str
    ) -> List[dict]:
        out = rows
        if topic_id:
            out = [r for r in out if r.get("topic_id") == topic_id]
        if chapter_id:
            out = [r for r in out if str(r.get("topic_id", "")).startswith(f"{chapter_id}-")]
        if grade_band:
            out = [r for r in out if str(r.get("grade_band", "")).strip() == grade_band]
        if difficulty:
            out = [r for r in out if str(r.get("difficulty", "")).strip() == difficulty]
        if method_tag:
            out = [r for r in out if method_tag in [str(x).strip() for x in r.get("method_tags", [])]]
        if q:
            out = [r for r in out if self._contains(r, q)]
        return out

    def _evidence_snippet(self, text: str, q: str, max_len: int = 80) -> dict:
        src = (text or "").strip()
        if not src:
            return {"snippet": "", "match_index": -1}
        if not q:
            return {"snippet": src[:max_len], "match_index": -1}
        ql = q.lower()
        sl = src.lower()
        idx = sl.find(ql)
        if idx < 0:
            return {"snippet": src[:max_len], "match_index": -1}
        left = max(0, idx - 24)
        right = min(len(src), idx + len(q) + 24)
        seg = src[left:right]
        seg = seg if len(seg) <= max_len else seg[:max_len]
        if left > 0:
            seg = f"...{seg}"
        if right < len(src):
            seg = f"{seg}..."
        return {"snippet": seg, "match_index": idx}

    def _find_line_hint(self, source_ref: dict, q: str) -> int:
        if not q:
            return -1
        text_path = str(source_ref.get("text_path", "")).strip()
        if not text_path:
            return -1
        abs_path = (self.state.project_root / text_path).resolve()
        if not abs_path.exists():
            return -1
        try:
            with abs_path.open("r", encoding="utf-8", errors="ignore") as f:
                ql = q.lower()
                for idx, line in enumerate(f, start=1):
                    if ql in line.lower():
                        return idx
        except Exception:
            return -1
        return -1

    def _build_evidence(self, row: dict, q: str) -> dict:
        fields: List[dict] = []
        for key in ("title", "stem", "difficulty", "grade_band"):
            val = row.get(key)
            if isinstance(val, str) and val.strip() and (not q or q.lower() in val.lower()):
                fields.append({"field": key, **self._evidence_snippet(val, q)})
                if len(fields) >= 3:
                    break
        if len(fields) < 3:
            for key in ("method_tags", "learning_objectives", "common_mistakes", "analysis_steps"):
                val = row.get(key)
                if isinstance(val, list):
                    for item in val:
                        if not isinstance(item, str) or not item.strip():
                            continue
                        if q and q.lower() not in item.lower():
                            continue
                        fields.append({"field": key, **self._evidence_snippet(item, q)})
                        if len(fields) >= 3:
                            break
                if len(fields) >= 3:
                    break
        source_ref = row.get("source_ref", {}) if isinstance(row.get("source_ref"), dict) else {}
        line_hint = self._find_line_hint(source_ref, q)
        return {
            "query": q,
            "fields": fields,
            "source_locator": {
                "topic_id": str(row.get("topic_id", "")).strip(),
                "problem_id": str(row.get("problem_id", "")).strip(),
                "asset_id": str(source_ref.get("asset_id", "")).strip(),
                "file_path": str(source_ref.get("file_path", "")).strip(),
                "text_path": str(source_ref.get("text_path", "")).strip(),
                "line_hint": line_hint,
            },
        }

    def _search(self, audience: str, q: str, chapter_id: str, grade_band: str, difficulty: str, method_tag: str, limit: int) -> dict:
        topic_rows = [r for r in self.state.cache[f"topics_{audience}"] if self._contains(r, q)]
        problem_rows = [r for r in self.state.cache[f"problems_{audience}"] if self._contains(r, q)]
        if chapter_id:
            topic_rows = [r for r in topic_rows if str(r.get("topic_id", "")).startswith(f"{chapter_id}-")]
            problem_rows = [r for r in problem_rows if str(r.get("topic_id", "")).startswith(f"{chapter_id}-")]
        if grade_band:
            problem_rows = [r for r in problem_rows if str(r.get("grade_band", "")).strip() == grade_band]
        if difficulty:
            problem_rows = [r for r in problem_rows if str(r.get("difficulty", "")).strip() == difficulty]
        if method_tag:
            problem_rows = [r for r in problem_rows if method_tag in [str(x).strip() for x in r.get("method_tags", [])]]
        topic_total = len(topic_rows)
        problem_total = len(problem_rows)
        topic_out = [{**r, "evidence": self._build_evidence(r, q)} for r in topic_rows[:limit]]
        problem_out = [{**r, "evidence": self._build_evidence(r, q)} for r in problem_rows[:limit]]
        return {
            "data": {"topics": topic_out, "problems": problem_out},
            "meta": {"topic_total": topic_total, "problem_total": problem_total, "limit": limit},
        }

    def _read_json_body(self) -> Tuple[dict, str]:
        raw_len = self.headers.get("Content-Length", "0").strip()
        try:
            length = int(raw_len)
        except ValueError:
            return {}, "invalid content-length"
        if length <= 0:
            return {}, "empty body"
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return {}, "invalid json body"
        if not isinstance(payload, dict):
            return {}, "json body must be object"
        return payload, ""

    def _auth_summary(self) -> dict:
        auth_enabled = bool(self.state.cache.get("auth_enabled", False))
        public_paths = sorted(list(self.state.cache.get("public_paths", set())))
        auth = getattr(self, "_auth_context", {})
        return {
            "auth_enabled": auth_enabled,
            "public_paths": public_paths,
            "authorized": auth.get("authorized", False),
            "auth_reason": auth.get("reason", ""),
            "api_key_id": auth.get("api_key_id", ""),
            "api_key_name": auth.get("api_key_name", ""),
            "allow_all": auth.get("allow_all", False),
            "allow_prefixes": auth.get("allow_prefixes", []),
            "allow_audiences": auth.get("allow_audiences", []),
            "audience_hint": auth.get("audience_hint", ""),
            "revoked_reason": auth.get("revoked_reason", ""),
            "config_mtime": int(self.state.cache.get("security_config_mtime", 0)),
            "rotation_group": auth.get("rotation_group", ""),
            "rotation_phase": auth.get("rotation_phase", ""),
        }

    def _rotation_check(self) -> dict:
        key_rules = self.state.cache.get("api_key_rules", {})
        revoked = self.state.cache.get("revoked_keys", {})
        groups = self.state.cache.get("rotation_groups", [])
        issues: List[dict] = []
        details: List[dict] = []
        for g in groups:
            old_key = str(g.get("old_key", "")).strip()
            new_key = str(g.get("new_key", "")).strip()
            phase = str(g.get("phase", "dual")).strip()
            name = str(g.get("name", "")).strip()
            old_rule = key_rules.get(old_key)
            new_rule = key_rules.get(new_key)
            old_exists = old_rule is not None
            new_exists = new_rule is not None
            old_disabled = bool(old_rule is not None and not bool(old_rule.get("enabled", True)))
            old_revoked = old_key in revoked
            if not old_exists:
                issues.append({"group": name, "level": "error", "code": "old_key_missing"})
            if not new_exists:
                issues.append({"group": name, "level": "error", "code": "new_key_missing"})
            if phase == "retire" and old_exists and not old_disabled and not old_revoked:
                issues.append({"group": name, "level": "warning", "code": "retire_old_not_disabled_or_revoked"})
            details.append(
                {
                    "name": name,
                    "phase": phase,
                    "old_key_id": self._key_id(old_key),
                    "new_key_id": self._key_id(new_key),
                    "old_key_exists": old_exists,
                    "new_key_exists": new_exists,
                    "old_key_disabled": old_disabled,
                    "old_key_revoked": old_revoked,
                }
            )
        return {"groups": details, "issues": issues, "ok": len([x for x in issues if x.get("level") == "error"]) == 0}

    def _tail_access_rows(self, limit: int = 2000) -> List[dict]:
        log_path = Path(str(self.state.cache.get("access_log_path", "")))
        if not str(log_path) or not log_path.exists():
            return []
        lines = log_path.read_text(encoding="utf-8").splitlines()
        rows: List[dict] = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except Exception:
                continue
        return rows

    def _tail_health_runs(self, limit: int = 200) -> List[dict]:
        history_path = Path(str(self.state.cache.get("health_history_path", "")))
        if not str(history_path) or not history_path.exists():
            return []
        lines = history_path.read_text(encoding="utf-8").splitlines()
        rows: List[dict] = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except Exception:
                continue
        return rows

    def _rotation_advice(self) -> dict:
        rows = self._tail_access_rows(3000)
        groups = self.state.cache.get("rotation_groups", [])
        advices: List[dict] = []
        for g in groups:
            phase = str(g.get("phase", "dual")).strip() or "dual"
            old_key = str(g.get("old_key", "")).strip()
            new_key = str(g.get("new_key", "")).strip()
            old_id = self._key_id(old_key)
            new_id = self._key_id(new_key)
            old_ok = sum(1 for r in rows if r.get("api_key_id") == old_id and int(r.get("status", 0)) < 400)
            new_ok = sum(1 for r in rows if r.get("api_key_id") == new_id and int(r.get("status", 0)) < 400)
            old_rotated_out = sum(
                1
                for r in rows
                if r.get("api_key_id") == old_id and int(r.get("status", 0)) == 401 and r.get("auth_reason") in ("key_rotated_out", "key_retired")
            )
            suggestion = "monitor"
            if phase == "dual" and new_ok >= 1:
                suggestion = "can_cutover"
            elif phase == "cutover" and old_rotated_out >= 1 and new_ok >= 1:
                suggestion = "can_retire"
            elif phase == "retire":
                suggestion = "stable"
            advices.append(
                {
                    "name": str(g.get("name", "")).strip(),
                    "phase": phase,
                    "old_key_id": old_id,
                    "new_key_id": new_id,
                    "old_success_count": old_ok,
                    "new_success_count": new_ok,
                    "old_blocked_count": old_rotated_out,
                    "suggestion": suggestion,
                }
            )
        return {"groups": advices, "window": len(rows)}

    def _rotation_gate(self) -> dict:
        gate_conf = self.state.cache.get("rotation_gate", {})
        min_consecutive_ok = int(gate_conf.get("min_consecutive_ok", 2) or 2)
        history = self._tail_health_runs(500)
        recent_ok = 0
        for row in reversed(history):
            if bool(row.get("ok", False)):
                recent_ok += 1
            else:
                break
        rotation_check = self._rotation_check()
        advice = self._rotation_advice()
        blockers: List[dict] = []
        if recent_ok < min_consecutive_ok:
            blockers.append({"code": "insufficient_consecutive_ok", "detail": f"{recent_ok}<{min_consecutive_ok}"})
        if bool(gate_conf.get("require_rotation_check_ok", True)) and not bool(rotation_check.get("ok", False)):
            blockers.append({"code": "rotation_check_failed", "detail": "rotation_check not ok"})
        for row in advice.get("groups", []):
            phase = str(row.get("phase", "")).strip()
            suggestion = str(row.get("suggestion", "")).strip()
            if phase == "dual" and suggestion not in ("can_cutover", "stable"):
                blockers.append({"code": "dual_not_ready", "group": row.get("name", ""), "detail": suggestion})
            if phase == "cutover" and suggestion not in ("can_retire", "stable"):
                blockers.append({"code": "cutover_not_ready", "group": row.get("name", ""), "detail": suggestion})
        return {
            "can_promote": len(blockers) == 0,
            "blockers": blockers,
            "min_consecutive_ok": min_consecutive_ok,
            "recent_consecutive_ok": recent_ok,
            "rotation_check_ok": bool(rotation_check.get("ok", False)),
            "advice": advice.get("groups", []),
        }

    def _rotation_plan(self) -> dict:
        gate = self._rotation_gate()
        advice_rows = gate.get("advice", [])
        plans: List[dict] = []
        for row in advice_rows:
            phase = str(row.get("phase", "")).strip()
            suggestion = str(row.get("suggestion", "")).strip()
            target_phase = phase
            if phase == "dual" and suggestion == "can_cutover":
                target_phase = "cutover"
            elif phase == "cutover" and suggestion == "can_retire":
                target_phase = "retire"
            eligible = bool(gate.get("can_promote", False)) and target_phase != phase
            plans.append(
                {
                    "name": row.get("name", ""),
                    "current_phase": phase,
                    "suggestion": suggestion,
                    "target_phase": target_phase,
                    "eligible": eligible,
                }
            )
        return {"can_promote": bool(gate.get("can_promote", False)), "blockers": gate.get("blockers", []), "plans": plans}

    def _pick_quality_metric(self, metric: str, source: str) -> float | None:
        quality = self.state.cache.get("quality_report", {})
        validation = self.state.cache.get("validation_report", {})
        if "." in source:
            top, section = source.split(".", 1)
        else:
            top, section = source, ""
        top = top.strip()
        section = section.strip()
        value = None
        if top == "quality":
            block = quality.get(section, {}) if section else quality
            value = block.get(metric)
        elif top == "validation":
            block = validation.get(section, {}) if section else validation
            value = block.get(metric)
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _quality_rule_passed(self, value: float | None, operator: str, threshold: float) -> bool:
        if value is None:
            return False
        if operator == ">=":
            return value >= threshold
        if operator == "<=":
            return value <= threshold
        if operator == ">":
            return value > threshold
        if operator == "<":
            return value < threshold
        if operator == "==":
            return abs(value - threshold) < 1e-9
        return False

    def _quality_gate_evaluate(self, profile: str = "", knowledge_version: str = "") -> dict:
        gate_conf = self.state.cache.get("quality_gate_profiles", {})
        default_profile = str(gate_conf.get("default_profile", "staging")).strip() or "staging"
        selected_profile = str(profile).strip() or default_profile
        profiles = gate_conf.get("profiles", {})
        selected = profiles.get(selected_profile)
        if not isinstance(selected, dict):
            return {
                "profile": selected_profile,
                "knowledge_version": knowledge_version,
                "can_release": False,
                "blockers": [{"code": "profile_not_found", "detail": selected_profile}],
                "warnings": [],
                "hard_results": [],
                "soft_results": [],
            }
        hard_results: List[dict] = []
        soft_results: List[dict] = []
        blockers: List[dict] = []
        warnings: List[dict] = []
        for rule in selected.get("hard_rules", []):
            metric = str(rule.get("metric", "")).strip()
            source = str(rule.get("source", "")).strip()
            operator = str(rule.get("operator", "")).strip()
            threshold = float(rule.get("threshold", 0.0))
            value = self._pick_quality_metric(metric, source)
            passed = self._quality_rule_passed(value, operator, threshold)
            item = {
                "metric": metric,
                "source": source,
                "operator": operator,
                "threshold": threshold,
                "value": value,
                "passed": passed,
            }
            hard_results.append(item)
            if not passed:
                blockers.append({"code": "hard_rule_failed", **item})
        for rule in selected.get("soft_rules", []):
            metric = str(rule.get("metric", "")).strip()
            source = str(rule.get("source", "")).strip()
            operator = str(rule.get("operator", "")).strip()
            threshold = float(rule.get("threshold", 0.0))
            value = self._pick_quality_metric(metric, source)
            passed = self._quality_rule_passed(value, operator, threshold)
            item = {
                "metric": metric,
                "source": source,
                "operator": operator,
                "threshold": threshold,
                "value": value,
                "passed": passed,
            }
            soft_results.append(item)
            if not passed:
                warnings.append({"code": "soft_rule_failed", **item})
        return {
            "profile": selected_profile,
            "knowledge_version": knowledge_version,
            "can_release": len(blockers) == 0,
            "blockers": blockers,
            "warnings": warnings,
            "hard_results": hard_results,
            "soft_results": soft_results,
        }

    def _problem_facets(self, rows: List[dict]) -> dict:
        return {
            "grade_band": self._distribution(rows, "grade_band"),
            "difficulty": self._distribution(rows, "difficulty"),
            "method_tag_source": self._distribution(rows, "method_tag_source"),
            "grade_source": self._distribution(rows, "grade_source"),
            "difficulty_source": self._distribution(rows, "difficulty_source"),
        }

    def do_POST(self) -> None:
        self._trace_id = self._new_trace()
        parsed = urlparse(self.path)
        path = parsed.path
        payload: dict = {}
        if path in ("/search", "/quality/gate/evaluate"):
            payload, err = self._read_json_body()
            if err:
                self._bad_request(err)
                return
        audience_hint = str(payload.get("audience", "")).strip()
        ok, ctx = self._authorize(path, audience_hint=audience_hint)
        self._auth_context = ctx
        if not ok:
            self._unauthorized("missing or invalid api key")
            return
        if path == "/quality/gate/evaluate":
            profile = str(payload.get("gate_profile", "")).strip()
            knowledge_version = str(payload.get("knowledge_version", "")).strip()
            data = self._quality_gate_evaluate(profile=profile, knowledge_version=knowledge_version)
            self._json(200, {"code": 0, "message": "ok", "data": data})
            return
        if path != "/search":
            self._json(404, {"code": 404, "message": "not found", "data": None})
            return
        audience = str(payload.get("audience", "teacher")).strip()
        if audience not in ("teacher", "student"):
            self._bad_request("invalid audience")
            return
        q = str(payload.get("q", "")).strip()
        if not q:
            self._bad_request("missing q")
            return
        chapter_id = str(payload.get("chapter_id", "")).strip()
        grade_band = str(payload.get("grade_band", "")).strip()
        difficulty = str(payload.get("difficulty", "")).strip()
        method_tag = str(payload.get("method_tag", "")).strip()
        limit = payload.get("limit", 10)
        try:
            limit_int = int(limit)
        except Exception:
            self._bad_request("invalid limit")
            return
        if limit_int < 1 or limit_int > 500:
            self._bad_request("limit out of range [1,500]")
            return
        result = self._search(audience, q, chapter_id, grade_band, difficulty, method_tag, limit_int)
        self._json(200, {"code": 0, "message": "ok", "data": result["data"], "meta": result["meta"]})

    def do_GET(self) -> None:
        self._trace_id = self._new_trace()
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        audience_hint = self._get_text_param(qs, "audience", "")
        ok, ctx = self._authorize(path, audience_hint=audience_hint)
        self._auth_context = ctx
        if not ok:
            self._unauthorized("missing or invalid api key")
            return
        audience = self._get_text_param(qs, "audience", "teacher")
        if audience not in ("teacher", "student"):
            self._bad_request("invalid audience")
            return

        if path == "/health":
            self._json(200, {"code": 0, "message": "ok", "data": {"status": "up"}})
            return
        if path == "/reload":
            self.state.reload()
            self._json(200, {"code": 0, "message": "ok", "data": {"reloaded": True}})
            return
        if path == "/catalog/chapters":
            rows = sorted(self.state.cache.get("chapter_graph_map", {}).values(), key=lambda x: x.get("chapter_id", ""))
            q = self._get_text_param(qs, "q", "")
            if q:
                rows = [r for r in rows if q in r.get("chapter_id", "")]
            limit, err = self._get_int_param(qs, "limit", 100, 1, 500)
            if err:
                self._bad_request(err)
                return
            offset, err = self._get_int_param(qs, "offset", 0, 0, 100000)
            if err:
                self._bad_request(err)
                return
            self._json(
                200,
                {
                    "code": 0,
                    "message": "ok",
                    "data": rows[offset : offset + limit],
                    "meta": {"total": len(rows), "offset": offset, "limit": limit},
                },
            )
            return
        if path == "/topics":
            rows = self.state.cache[f"topics_{audience}"]
            q = self._get_text_param(qs, "q", "")
            chapter_id = self._get_text_param(qs, "chapter_id", "")
            domain = self._get_text_param(qs, "domain", "")
            grade_band = self._get_text_param(qs, "grade_band", "")
            difficulty = self._get_text_param(qs, "difficulty", "")
            has_pre, err = self._get_bool_param(qs, "has_prerequisites")
            if err:
                self._bad_request(err)
                return
            has_obj, err = self._get_bool_param(qs, "has_learning_objectives")
            if err:
                self._bad_request(err)
                return
            rows = self._filter_topics(rows, audience, q, chapter_id, domain, grade_band, difficulty, has_pre, has_obj)
            order_by = self._get_text_param(qs, "order_by", "topic_id")
            order = self._get_text_param(qs, "order", "asc")
            if order not in ("asc", "desc"):
                self._bad_request("invalid order")
                return
            rows = self._sort_rows(rows, order_by, order)
            limit, err = self._get_int_param(qs, "limit", 20, 1, 500)
            if err:
                self._bad_request(err)
                return
            offset, err = self._get_int_param(qs, "offset", 0, 0, 100000)
            if err:
                self._bad_request(err)
                return
            self._json(
                200,
                {
                    "code": 0,
                    "message": "ok",
                    "data": rows[offset : offset + limit],
                    "meta": {"total": len(rows), "offset": offset, "limit": limit},
                },
            )
            return
        if path.startswith("/topics/"):
            topic_id = path.split("/topics/", 1)[1]
            rows = self.state.cache[f"topics_{audience}"]
            found = next((r for r in rows if r.get("topic_id") == topic_id), None)
            if not found:
                self._json(404, {"code": 404, "message": "not found", "data": None})
                return
            graph = self.state.cache.get("graph_map", {}).get(topic_id, {"prerequisites": [], "next_topics": []})
            chapter_id = "-".join(topic_id.split("-")[:2]) if "-" in topic_id else topic_id
            chapter_graph = self.state.cache.get("chapter_graph_map", {}).get(chapter_id, {})
            stats = self._topic_problem_stats(audience, topic_id)
            self._json(
                200,
                {
                    "code": 0,
                    "message": "ok",
                    "data": {
                        **found,
                        "graph": graph,
                        "chapter_id": chapter_id,
                        "chapter_graph": chapter_graph,
                        "problem_stats": stats,
                    },
                },
            )
            return
        if path == "/problems":
            rows = self.state.cache[f"problems_{audience}"]
            topic_id = self._get_text_param(qs, "topic_id", "")
            chapter_id = self._get_text_param(qs, "chapter_id", "")
            grade_band = self._get_text_param(qs, "grade_band", "")
            difficulty = self._get_text_param(qs, "difficulty", "")
            method_tag = self._get_text_param(qs, "method_tag", "")
            q = self._get_text_param(qs, "q", "")
            rows = self._filter_problems(rows, topic_id, chapter_id, grade_band, difficulty, method_tag, q)
            order_by = self._get_text_param(qs, "order_by", "topic_id")
            order = self._get_text_param(qs, "order", "asc")
            if order not in ("asc", "desc"):
                self._bad_request("invalid order")
                return
            rows = self._sort_rows(rows, order_by, order)
            limit, err = self._get_int_param(qs, "limit", 20, 1, 500)
            if err:
                self._bad_request(err)
                return
            offset, err = self._get_int_param(qs, "offset", 0, 0, 100000)
            if err:
                self._bad_request(err)
                return
            self._json(
                200,
                {
                    "code": 0,
                    "message": "ok",
                    "data": rows[offset : offset + limit],
                    "meta": {"total": len(rows), "offset": offset, "limit": limit},
                },
            )
            return
        if path.startswith("/problems/"):
            problem_id = path.split("/problems/", 1)[1]
            rows = self.state.cache[f"problems_{audience}"]
            found = next((r for r in rows if str(r.get("problem_id", "")).strip() == problem_id), None)
            if not found:
                self._json(404, {"code": 404, "message": "not found", "data": None})
                return
            self._json(200, {"code": 0, "message": "ok", "data": found})
            return
        if path == "/facets/problems":
            rows = self.state.cache[f"problems_{audience}"]
            topic_id = self._get_text_param(qs, "topic_id", "")
            if topic_id:
                rows = [r for r in rows if r.get("topic_id") == topic_id]
            chapter_id = self._get_text_param(qs, "chapter_id", "")
            if chapter_id:
                rows = [r for r in rows if str(r.get("topic_id", "")).startswith(f"{chapter_id}-")]
            q = self._get_text_param(qs, "q", "")
            if q:
                rows = [r for r in rows if self._contains(r, q)]
            self._json(200, {"code": 0, "message": "ok", "data": self._problem_facets(rows), "meta": {"total": len(rows)}})
            return
        if path == "/search":
            q = self._get_text_param(qs, "q", "")
            if not q:
                self._bad_request("missing q")
                return
            limit, err = self._get_int_param(qs, "limit", 10, 1, 500)
            if err:
                self._bad_request(err)
                return
            grade_band = self._get_text_param(qs, "grade_band", "")
            difficulty = self._get_text_param(qs, "difficulty", "")
            chapter_id = self._get_text_param(qs, "chapter_id", "")
            method_tag = self._get_text_param(qs, "method_tag", "")
            result = self._search(audience, q, chapter_id, grade_band, difficulty, method_tag, limit)
            self._json(
                200,
                {
                    "code": 0,
                    "message": "ok",
                    "data": result["data"],
                    "meta": result["meta"],
                },
            )
            return
        if path == "/graph/validation":
            report = self.state.cache.get("graph_validation", {})
            self._json(200, {"code": 0, "message": "ok", "data": report})
            return
        if path.startswith("/graph/chapter/"):
            chapter_id = path.split("/graph/chapter/", 1)[1]
            graph_map = self.state.cache.get("chapter_graph_map", {})
            found = graph_map.get(chapter_id)
            if not found:
                self._json(404, {"code": 404, "message": "not found", "data": None})
                return
            self._json(200, {"code": 0, "message": "ok", "data": found})
            return
        if path.startswith("/graph/"):
            topic_id = path.split("/graph/", 1)[1]
            graph_map = self.state.cache.get("graph_map", {})
            found = graph_map.get(topic_id)
            if not found:
                self._json(404, {"code": 404, "message": "not found", "data": None})
                return
            self._json(200, {"code": 0, "message": "ok", "data": found})
            return
        if path == "/quality/summary":
            report = self.state.cache.get("quality_report", {})
            self._json(200, {"code": 0, "message": "ok", "data": report})
            return
        if path == "/quality/validation":
            report = self.state.cache.get("validation_report", {})
            self._json(200, {"code": 0, "message": "ok", "data": report})
            return
        if path == "/quality/gate/report":
            report = self.state.cache.get("quality_gate_report", {})
            self._json(200, {"code": 0, "message": "ok", "data": report})
            return
        if path == "/quality/gate/evaluate":
            profile = self._get_text_param(qs, "gate_profile", "")
            knowledge_version = self._get_text_param(qs, "knowledge_version", "")
            data = self._quality_gate_evaluate(profile=profile, knowledge_version=knowledge_version)
            self._json(200, {"code": 0, "message": "ok", "data": data})
            return
        if path == "/auth/whoami":
            self._json(200, {"code": 0, "message": "ok", "data": self._auth_summary()})
            return
        if path == "/auth/config":
            self._json(
                200,
                {
                    "code": 0,
                    "message": "ok",
                    "data": {
                        "auth_enabled": bool(self.state.cache.get("auth_enabled", False)),
                        "public_paths": sorted(list(self.state.cache.get("public_paths", set()))),
                        "api_key_count": len(self.state.cache.get("api_key_rules", {})),
                        "revoked_key_count": len(self.state.cache.get("revoked_keys", {})),
                        "config_mtime": int(self.state.cache.get("security_config_mtime", 0)),
                    },
                },
            )
            return
        if path == "/auth/reload":
            self.state.reload()
            self._json(200, {"code": 0, "message": "ok", "data": {"reloaded": True}})
            return
        if path == "/auth/rotation":
            rows = self.state.cache.get("rotation_groups", [])
            self._json(200, {"code": 0, "message": "ok", "data": rows, "meta": {"total": len(rows)}})
            return
        if path == "/auth/rotation/check":
            data = self._rotation_check()
            self._json(200, {"code": 0, "message": "ok", "data": data})
            return
        if path == "/auth/rotation/advice":
            data = self._rotation_advice()
            self._json(200, {"code": 0, "message": "ok", "data": data})
            return
        if path == "/auth/rotation/gate":
            data = self._rotation_gate()
            self._json(200, {"code": 0, "message": "ok", "data": data})
            return
        if path == "/auth/rotation/plan":
            data = self._rotation_plan()
            self._json(200, {"code": 0, "message": "ok", "data": data})
            return
        self._json(404, {"code": 404, "message": "not found", "data": None})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()

    state = AppState(Path(args.project_root).resolve())
    Handler.state = state
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(json.dumps({"host": args.host, "port": args.port, "status": "started"}, ensure_ascii=False))
    server.serve_forever()


if __name__ == "__main__":
    main()
