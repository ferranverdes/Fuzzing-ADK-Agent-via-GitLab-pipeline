#!/usr/bin/env python3
"""
Convert a FuzzyAI report.json file into a GitLab DAST report.

Usage:
    python fuzzyai_to_gitlab_dast.py <input_report.json> <output_gl_dast.json>

Optional environment variables:
    FUZZYAI_TARGET_URL
        Full URL of the tested LLM endpoint.
        Default: https://example.invalid/v1/chat/completions

    FUZZYAI_HTTP_METHOD
        HTTP method for the tested endpoint.
        Default: POST

    FUZZYAI_SEVERITY
        Default GitLab severity for emitted findings.
        Default: High
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlsplit


DEFAULT_TARGET_URL = os.getenv(
    "FUZZYAI_TARGET_URL",
    "https://example.invalid/v1/chat/completions",
).strip()
DEFAULT_HTTP_METHOD = os.getenv("FUZZYAI_HTTP_METHOD", "POST").strip().upper()
DEFAULT_SEVERITY = os.getenv("FUZZYAI_SEVERITY", "High").strip().capitalize()


def iso_now_gitlab() -> str:
    # GitLab DAST schema expects yyyy-mm-ddThh:mm:ss without timezone suffix.
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def slugify(value: str, max_len: int = 80) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^a-z0-9._-]", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:max_len] or "unknown"


def truncate(text: str, max_len: int = 4000) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def severity_for_prompt(original_prompt: str, attack_mode: str) -> str:
    prompt = original_prompt.lower()

    if "malware" in prompt:
        return "Critical"
    if "bypass safety filters" in prompt:
        return "High"
    if "illegal" in prompt:
        return "Medium"
    if attack_mode.lower() == "dan":
        return "High"

    return DEFAULT_SEVERITY


def confidence_from_classifier(classifications: Dict[str, Any]) -> str:
    value = classifications.get("OPENAI_MODERATION_CLASSIFIER")
    return "High" if value == 1 else "Medium"


def parse_target_url(url: str) -> Tuple[str, str]:
    parsed = urlsplit(url)

    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            f"FUZZYAI_TARGET_URL must be a full URL with scheme and host, got: {url!r}"
        )

    hostname = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    return hostname, path


def make_primary_identifier(
    original_prompt: str, attack_mode: str, model_name: str
) -> Dict[str, str]:
    key = f"fuzzyai:jailbreak:{model_name}:{attack_mode}:{original_prompt}"
    stable = "fuzzyai-jailbreak-" + slugify(
        f"{model_name}-{attack_mode}-{original_prompt}", 120
    )

    return {
        "type": "fuzzyai",
        "name": stable,
        "value": stable,
        "url": f"https://example.invalid/fuzzyai/rules/{sha256_hex(key)}",
    }


def make_cwe_identifier() -> Dict[str, str]:
    return {
        "type": "cwe",
        "name": "CWE-184",
        "value": "CWE-184",
        "url": "https://cwe.mitre.org/data/definitions/184.html",
    }


def make_details(
    attack_id: str,
    model_name: str,
    attack_mode: str,
    original_prompt: str,
    harmful_prompt: str,
    harmful_response: str,
    classifications: Dict[str, Any],
) -> Dict[str, Dict[str, str]]:
    return {
        "attack_id": {
            "type": "text",
            "name": "Attack ID",
            "value": attack_id,
        },
        "model_name": {
            "type": "text",
            "name": "Model name",
            "value": model_name,
        },
        "attack_mode": {
            "type": "text",
            "name": "Attack mode",
            "value": attack_mode,
        },
        "original_prompt": {
            "type": "text",
            "name": "Original prompt",
            "value": truncate(original_prompt, 2000),
        },
        "harmful_prompt": {
            "type": "text",
            "name": "Adversarial prompt",
            "value": truncate(harmful_prompt, 12000),
        },
        "harmful_response": {
            "type": "text",
            "name": "Model response evidence",
            "value": truncate(harmful_response, 12000),
        },
        "moderation_classifier": {
            "type": "text",
            "name": "OPENAI_MODERATION_CLASSIFIER",
            "value": str(classifications.get("OPENAI_MODERATION_CLASSIFIER", "")),
        },
    }


def make_vulnerability(
    *,
    attack_id: str,
    attack_mode: str,
    model_name: str,
    entry: Dict[str, Any],
    target_url: str,
    http_method: str,
) -> Dict[str, Any]:
    original_prompt = entry.get("original_prompt", "").strip()
    harmful_prompt = entry.get("harmful_prompt", "").strip()
    harmful_response = entry.get("harmful_response", "").strip()
    classifications = entry.get("classifications", {}) or {}

    identifier = make_primary_identifier(original_prompt, attack_mode, model_name)
    severity = severity_for_prompt(original_prompt, attack_mode)
    confidence = confidence_from_classifier(classifications)
    hostname, path = parse_target_url(target_url)

    evidence_hash_basis = (
        f"{attack_id}|{attack_mode}|{model_name}|"
        f"{original_prompt}|{harmful_prompt}|{harmful_response}"
    )

    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, evidence_hash_basis)),
        "category": "dast",
        "name": f"LLM jailbreak via '{attack_mode}' prompt injection",
        "description": (
            "The tested LLM endpoint produced unsafe or policy-violating content "
            f"after a jailbreak attempt using the '{attack_mode}' attack mode."
        ),
        "description_html": (
            "The tested LLM endpoint produced unsafe or policy-violating content "
            f"after a jailbreak attempt using the <code>{attack_mode}</code> attack mode."
        ),
        "severity": severity,
        "confidence": confidence,
        "solution": (
            "Strengthen system instructions, add structured input validation, "
            "enforce output-side safety filtering, block known jailbreak patterns, "
            "and retest the endpoint with the same adversarial prompts."
        ),
        "scanner": {
            "id": "fuzzyai",
            "name": "FuzzyAI",
        },
        "identifiers": [
            identifier,
            make_cwe_identifier(),
        ],
        "location": {
            "hostname": hostname,
            "path": path,
            "method": http_method,
        },
        "details": make_details(
            attack_id=attack_id,
            model_name=model_name,
            attack_mode=attack_mode,
            original_prompt=original_prompt,
            harmful_prompt=harmful_prompt,
            harmful_response=harmful_response,
            classifications=classifications,
        ),
    }


def extract_vulnerabilities(
    report: Dict[str, Any], target_url: str, http_method: str
) -> List[Dict[str, Any]]:
    attack_id = report.get("attack_id", "")
    vulnerabilities: List[Dict[str, Any]] = []

    for technique in report.get("attacking_techniques", []):
        attack_mode = technique.get("attack_mode", "unknown")

        for model in technique.get("models", []):
            model_name = model.get("name", "unknown")

            for entry in model.get("harmful_prompts", []):
                vulnerabilities.append(
                    make_vulnerability(
                        attack_id=attack_id,
                        attack_mode=attack_mode,
                        model_name=model_name,
                        entry=entry,
                        target_url=target_url,
                        http_method=http_method,
                    )
                )

    return vulnerabilities


def build_scan_section(target_url: str, http_method: str) -> Dict[str, Any]:
    ts = iso_now_gitlab()

    return {
        "analyzer": {
            "id": "fuzzyai",
            "name": "FuzzyAI",
            "vendor": {"name": "Custom"},
            "version": "unknown",
            "url": "https://github.com/cyberark/FuzzyAI",
        },
        "scanner": {
            "id": "fuzzyai",
            "name": "FuzzyAI",
            "vendor": {"name": "Custom"},
            "version": "unknown",
            "url": "https://github.com/cyberark/FuzzyAI",
        },
        "type": "dast",
        "status": "success",
        "start_time": ts,
        "end_time": ts,
        "scanned_resources": [
            {
                "type": "url",
                "method": http_method,
                "url": target_url,
            }
        ],
    }


def build_report(
    report: Dict[str, Any], vulnerabilities: List[Dict[str, Any]]
) -> Dict[str, Any]:
    return {
        "version": "15.2.4",
        "scan": build_scan_section(DEFAULT_TARGET_URL, DEFAULT_HTTP_METHOD),
        "vulnerabilities": vulnerabilities,
        "remediations": [],
    }


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: python fuzzyai_to_gitlab_dast.py <input_report.json> <output_gl_dast.json>",
            file=sys.stderr,
        )
        return 1

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"Input file does not exist: {input_path}", file=sys.stderr)
        return 2

    try:
        parse_target_url(DEFAULT_TARGET_URL)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    report = read_json(input_path)
    vulnerabilities = extract_vulnerabilities(
        report,
        target_url=DEFAULT_TARGET_URL,
        http_method=DEFAULT_HTTP_METHOD,
    )
    gitlab_report = build_report(report, vulnerabilities)
    write_json(output_path, gitlab_report)

    print(
        f"Wrote {len(vulnerabilities)} vulnerabilities to {output_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
