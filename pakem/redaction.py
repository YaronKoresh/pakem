from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass


@dataclass(frozen=True)
class SensitiveFinding:
    kind: str
    count: int


_REDACTION_RULES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "aws_access_key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED_AWS_ACCESS_KEY]",
    ),
    (
        "github_token",
        re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    (
        "private_key_block",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        "password_assignment",
        re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]+['\"]"),
        "[REDACTED_PASSWORD_ASSIGNMENT]",
    ),
    (
        "secret_assignment",
        re.compile(
            r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"][^'\"]+['\"]"
        ),
        "[REDACTED_SECRET_ASSIGNMENT]",
    ),
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        "phone",
        re.compile(
            r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b"
        ),
        "[REDACTED_PHONE]",
    ),
]


def apply_sensitive_data_policy(
    text: str, policy: str, scanner_mode: str = "builtin"
) -> tuple[str, list[SensitiveFinding]]:
    mode = str(policy or "off").lower()
    if mode not in {"off", "warn", "redact", "block"}:
        mode = "off"

    if mode == "off":
        return text, []

    findings: list[SensitiveFinding] = []
    output = text

    for kind, pattern, replacement in _REDACTION_RULES:
        matches = list(
            pattern.finditer(text if mode in {"warn", "block"} else output)
        )
        if not matches:
            continue
        findings.append(SensitiveFinding(kind=kind, count=len(matches)))
        if mode == "redact":
            output = pattern.sub(replacement, output)

    external = _scan_external_secret_tools(
        output if mode == "redact" else text, scanner_mode
    )
    if external > 0:
        findings.append(
            SensitiveFinding(kind="external_secret_scanner", count=external)
        )

    return output, findings


def _scan_external_secret_tools(text: str, scanner_mode: str) -> int:
    mode = str(scanner_mode or "builtin").lower()
    if mode in {"off", "builtin"}:
        return 0

    if mode == "auto":
        if shutil.which("gitleaks"):
            return _scan_with_gitleaks(text)
        if shutil.which("trufflehog"):
            return _scan_with_trufflehog(text)
        return 0

    if mode == "gitleaks":
        return _scan_with_gitleaks(text)

    if mode == "trufflehog":
        return _scan_with_trufflehog(text)

    return 0


def _scan_with_gitleaks(text: str) -> int:
    if not shutil.which("gitleaks"):
        return 0

    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(text)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [
                "gitleaks",
                "detect",
                "--source",
                tmp_path,
                "--no-git",
                "--report-format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = (result.stdout or "").strip()
        if not output:
            return 0
        try:
            parsed = __import__("json").loads(output)
            if isinstance(parsed, list):
                return len(parsed)
            return 0
        except Exception:
            return output.count("\n") + 1
    except Exception:
        return 0
    finally:
        try:
            __import__("os").unlink(tmp_path)
        except Exception:
            pass


def _scan_with_trufflehog(text: str) -> int:
    if not shutil.which("trufflehog"):
        return 0

    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(text)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["trufflehog", "filesystem", "--json", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = (result.stdout or "").strip()
        if not output:
            return 0
        count = 0
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = __import__("json").loads(line)
                if isinstance(item, dict):
                    count += 1
            except Exception:
                continue
        return count
    except Exception:
        return 0
    finally:
        try:
            __import__("os").unlink(tmp_path)
        except Exception:
            pass
