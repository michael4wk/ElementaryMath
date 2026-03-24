#!/usr/bin/env python3
from __future__ import annotations

import re
from typing import List


NUM_RE = re.compile(r"\d+(?:\.\d+)?")
UNIT_RE = re.compile(r"(厘米|米|千米|克|千克|吨|平方厘米|平方分米|平方米|立方厘米|立方分米|立方米|小时|分钟|秒|元|角|分|%)")
STEP_HINT_RE = re.compile(r"(原式|解|步骤|思路|所以|因此|可得|设|则|=)")
TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")


def _token_set(text: str) -> set[str]:
    return {x.lower() for x in TOKEN_RE.findall(text or "") if x}


def semantic_consistency_confidence(stem: str, answer: str, analysis_steps: List[str]) -> float:
    stem_tokens = _token_set(stem or "")
    answer_tokens = _token_set(answer or "")
    analysis_tokens = _token_set(" ".join([str(x) for x in (analysis_steps or [])]))
    if not answer_tokens and not analysis_tokens:
        return 0.0
    stem_overlap = len(stem_tokens & analysis_tokens) / max(1, len(stem_tokens)) if stem_tokens else 0.0
    answer_overlap = len(answer_tokens & analysis_tokens) / max(1, len(answer_tokens)) if answer_tokens else 0.0
    raw = 0.6 * answer_overlap + 0.4 * stem_overlap
    return round(raw * 100.0, 2)


def classify_consistency_conflicts(stem: str, answer: str, analysis_steps: List[str]) -> List[str]:
    conflicts: List[str] = []
    stem_text = stem or ""
    answer_text = answer or ""
    steps = analysis_steps or []
    analysis_text = " ".join([str(x) for x in steps])

    if not answer_text.strip() and not steps:
        return ["answer_analysis_missing"]
    if not answer_text.strip():
        conflicts.append("answer_missing")
    if not steps:
        conflicts.append("analysis_missing")

    if answer_text.strip() == "【公式】":
        conflicts.append("answer_formula_placeholder")

    stem_nums = set(NUM_RE.findall(stem_text))
    answer_nums = set(NUM_RE.findall(answer_text))
    analysis_nums = set(NUM_RE.findall(analysis_text))
    if answer_nums and not (answer_nums & analysis_nums):
        conflicts.append("number_mismatch")
    if stem_nums and analysis_nums and len(stem_nums & analysis_nums) == 0:
        conflicts.append("analysis_not_grounded")

    stem_units = set(UNIT_RE.findall(stem_text))
    answer_units = set(UNIT_RE.findall(answer_text))
    analysis_units = set(UNIT_RE.findall(analysis_text))
    if answer_units and not (answer_units & analysis_units):
        conflicts.append("unit_mismatch")
    if stem_units and analysis_units and not (stem_units & analysis_units):
        conflicts.append("unit_not_grounded")

    if steps:
        step_hint_count = sum(1 for x in steps if STEP_HINT_RE.search(str(x)))
        if step_hint_count == 0:
            conflicts.append("step_structure_weak")

    confidence = semantic_consistency_confidence(stem_text, answer_text, steps)
    if confidence < 30.0:
        conflicts.append("semantic_weak_overlap")

    ordered: List[str] = []
    for code in conflicts:
        if code not in ordered:
            ordered.append(code)
    return ordered
