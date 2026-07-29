"""Robust parsers for audit tool outputs (Phase 0 / schema_version 2)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .statuses import PARSER_VERSION, ToolStatus


def safe_read(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def read_exit_code(report_path: Path) -> Optional[int]:
    """Read sidecar `<report>.exitcode` written by shell runners."""
    sidecar = Path(str(report_path) + ".exitcode")
    if not sidecar.exists():
        # Also accept stem.exitcode next to report
        alt = report_path.with_suffix(report_path.suffix + ".exitcode")
        if alt.exists():
            sidecar = alt
        else:
            sibling = report_path.parent / f"{report_path.name}.exitcode"
            if sibling.exists():
                sidecar = sibling
            else:
                return None
    try:
        text = sidecar.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        return int(text)
    except (OSError, ValueError, IndexError):
        return None


def extract_json_object(text: str) -> Optional[dict]:
    idx = text.find("{")
    if idx < 0:
        return None
    try:
        return json.loads(text[idx:])
    except json.JSONDecodeError:
        return None


def _note_unavailable(content: str) -> bool:
    lowered = content.lower()
    return "no instalado" in lowered or "not installed" in lowered or "command not found" in lowered


def _note_skipped(content: str) -> bool:
    lowered = content.lower()
    return "no ejecutado" in lowered or "no se detecto" in lowered or "omitido" in lowered


@dataclass
class ParsedToolResult:
    name: str
    status: str = ToolStatus.NOT_RUN.value
    severity: str = "none"
    metrics: Dict[str, int] = field(default_factory=dict)
    observation: str = ""
    exit_code: Optional[int] = None
    error: Optional[str] = None
    parser: str = ""
    parser_version: str = PARSER_VERSION

    def to_tool_dict(self, report: str) -> dict[str, Any]:
        return {
            "status": self.status,
            "severity": self.severity,
            "metrics": dict(self.metrics),
            "report": report,
            "observation": self.observation,
            "exit_code": self.exit_code,
            "error": self.error,
            "parser": self.parser or self.name.lower().replace(" ", "_"),
            "parser_version": self.parser_version,
        }


def parse_ruff(path: Path, *, exit_code: Optional[int] = None) -> ParsedToolResult:
    tr = ParsedToolResult("Ruff", parser="ruff")
    content = safe_read(path)
    tr.exit_code = exit_code if exit_code is not None else read_exit_code(path)
    if content is None:
        tr.status = ToolStatus.NOT_RUN.value
        tr.observation = "Reporte ausente."
        return tr
    if not content.strip():
        if tr.exit_code == 0:
            tr.status = ToolStatus.OK.value
            tr.metrics["issues"] = 0
            return tr
        tr.status = ToolStatus.EXECUTION_ERROR.value
        tr.error = "Salida vacía con exit code distinto de 0."
        tr.severity = "high"
        return tr
    if _note_unavailable(content):
        tr.status = ToolStatus.NOT_AVAILABLE.value
        tr.severity = "info"
        tr.observation = "Herramienta no disponible en el entorno resuelto."
        return tr
    if _note_skipped(content):
        tr.status = ToolStatus.SKIPPED.value
        tr.severity = "info"
        return tr
    if tr.exit_code is not None and tr.exit_code not in (0, 1):
        tr.status = ToolStatus.EXECUTION_ERROR.value
        tr.severity = "high"
        tr.error = f"Ruff exit code {tr.exit_code}"
        return tr
    if "All checks passed" in content or re.search(r"Found 0 errors", content):
        tr.status = ToolStatus.OK.value
        tr.metrics["issues"] = 0
        return tr
    m = re.search(r"Found (\d+) errors?", content)
    if m:
        issues = int(m.group(1))
        tr.metrics["issues"] = issues
        fx = re.search(r"(\d+)\s+fixable", content)
        if fx:
            tr.metrics["fixable"] = int(fx.group(1))
        tr.status = ToolStatus.FINDINGS.value if issues > 0 else ToolStatus.OK.value
        tr.severity = "medium" if issues > 0 else "none"
        return tr
    if tr.exit_code == 0:
        tr.status = ToolStatus.OK.value
        tr.metrics["issues"] = 0
        return tr
    if tr.exit_code == 1:
        # Findings present but summary line missing — count diagnostic lines loosely.
        issues = len(re.findall(r"^[^:\n]+:\d+:\d+:\s+[A-Z]\d+", content, flags=re.MULTILINE))
        tr.metrics["issues"] = issues
        tr.status = ToolStatus.FINDINGS.value if issues > 0 else ToolStatus.PARSE_ERROR.value
        tr.severity = "medium" if issues > 0 else "low"
        if issues == 0:
            tr.error = "Exit 1 sin resumen parseable."
        return tr
    tr.status = ToolStatus.PARSE_ERROR.value
    tr.severity = "low"
    tr.error = "No se pudo extraer métrica de Ruff."
    return tr


def parse_mypy(path: Path, *, exit_code: Optional[int] = None) -> ParsedToolResult:
    tr = ParsedToolResult("Mypy", parser="mypy")
    content = safe_read(path)
    tr.exit_code = exit_code if exit_code is not None else read_exit_code(path)
    if content is None:
        tr.status = ToolStatus.NOT_RUN.value
        return tr
    if _note_unavailable(content):
        tr.status = ToolStatus.NOT_AVAILABLE.value
        tr.severity = "info"
        return tr
    if _note_skipped(content):
        tr.status = ToolStatus.SKIPPED.value
        tr.severity = "info"
        return tr
    if tr.exit_code is not None and tr.exit_code not in (0, 1):
        tr.status = ToolStatus.EXECUTION_ERROR.value
        tr.error = f"Mypy exit code {tr.exit_code}"
        tr.severity = "high"
        return tr
    if "Success:" in content:
        tr.status = ToolStatus.OK.value
        tr.metrics["errors"] = 0
        return tr
    m = re.search(r"Found (\d+) errors? in (\d+) files?", content)
    if m:
        errs, files = int(m.group(1)), int(m.group(2))
        tr.metrics["errors"] = errs
        tr.metrics["files"] = files
        tr.status = ToolStatus.FINDINGS.value if errs > 0 else ToolStatus.OK.value
        tr.severity = "high" if errs > 0 else "none"
        return tr
    if "error:" in content.lower() and tr.exit_code in (None, 1):
        # Count mypy error lines carefully (file:line: error:)
        errs = len(re.findall(r":\d+:\s+error:", content))
        if errs == 0:
            errs = len(re.findall(r"^[^:\n]+:\d+: error:", content, flags=re.MULTILINE))
        tr.metrics["errors"] = errs
        if errs > 0:
            tr.status = ToolStatus.FINDINGS.value
            tr.severity = "high"
            return tr
    if tr.exit_code == 0:
        tr.status = ToolStatus.OK.value
        tr.metrics["errors"] = 0
        return tr
    tr.status = ToolStatus.PARSE_ERROR.value
    tr.severity = "low"
    tr.error = "No se pudo parsear salida de Mypy."
    return tr


def parse_bandit(path: Path, *, exit_code: Optional[int] = None) -> ParsedToolResult:
    tr = ParsedToolResult("Bandit", parser="bandit")
    content = safe_read(path)
    tr.exit_code = exit_code if exit_code is not None else read_exit_code(path)
    if content is None:
        tr.status = ToolStatus.NOT_RUN.value
        return tr
    if _note_unavailable(content):
        tr.status = ToolStatus.NOT_AVAILABLE.value
        tr.severity = "info"
        return tr
    if _note_skipped(content):
        tr.status = ToolStatus.SKIPPED.value
        tr.severity = "info"
        return tr
    data = extract_json_object(content)
    if data is None:
        tr.status = ToolStatus.PARSE_ERROR.value
        tr.severity = "high"
        tr.error = "JSON inválido o no parseable."
        return tr
    results = data.get("results", []) or []
    sev_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    blocking_high = 0
    for r in results:
        sev = str(r.get("issue_severity", "")).upper()
        if sev in sev_counts:
            sev_counts[sev] += 1
        conf = str(r.get("issue_confidence", "")).upper()
        # Policy: HIGH severity + HIGH/MEDIUM confidence → blocking (unless allowlisted via exceptions tooling).
        if sev == "HIGH" and conf in ("HIGH", "MEDIUM"):
            blocking_high += 1
    total = sum(sev_counts.values())
    tr.metrics.update(
        {
            "total": total,
            "high": sev_counts["HIGH"],
            "medium": sev_counts["MEDIUM"],
            "low": sev_counts["LOW"],
            "blocking_high": blocking_high,
        }
    )
    tr.status = ToolStatus.FINDINGS.value if total > 0 else ToolStatus.OK.value
    tr.severity = (
        "high"
        if blocking_high > 0 or sev_counts["HIGH"] > 0
        else ("medium" if sev_counts["MEDIUM"] > 0 else ("low" if total > 0 else "none"))
    )
    return tr


def parse_gitleaks(path: Path, *, exit_code: Optional[int] = None) -> ParsedToolResult:
    tr = ParsedToolResult("Gitleaks", parser="gitleaks")
    content = safe_read(path)
    tr.exit_code = exit_code if exit_code is not None else read_exit_code(path)
    if content is None:
        tr.status = ToolStatus.NOT_RUN.value
        tr.observation = "Reporte gitleaks ausente."
        return tr
    if _note_unavailable(content) or _note_skipped(content):
        tr.status = ToolStatus.NOT_AVAILABLE.value
        tr.severity = "high"
        tr.error = "gitleaks no ejecutado (docker/herramienta requerida)."
        return tr
    if tr.exit_code is not None and tr.exit_code not in (0, 1):
        tr.status = ToolStatus.EXECUTION_ERROR.value
        tr.severity = "high"
        tr.error = f"gitleaks exit {tr.exit_code}"
        return tr
    data = extract_json_object(content)
    # gitleaks JSON report is often a list of findings
    findings = 0
    if isinstance(data, list):
        findings = len(data)
    elif isinstance(data, dict):
        if "error" in data and not data.get("findings"):
            tr.status = ToolStatus.EXECUTION_ERROR.value
            tr.severity = "high"
            tr.error = str(data.get("error"))
            return tr
        findings = len(data.get("findings") or data.get("leaks") or [])
    else:
        # empty file / no leaks sometimes writes []
        stripped = content.strip()
        if stripped in ("", "[]", "null"):
            findings = 0
        else:
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    findings = len(parsed)
                else:
                    tr.status = ToolStatus.PARSE_ERROR.value
                    tr.error = "gitleaks JSON shape unexpected"
                    tr.severity = "high"
                    return tr
            except json.JSONDecodeError:
                tr.status = ToolStatus.PARSE_ERROR.value
                tr.error = "gitleaks JSON inválido"
                tr.severity = "high"
                return tr
    tr.metrics["secrets"] = findings
    tr.status = ToolStatus.FINDINGS.value if findings > 0 else ToolStatus.OK.value
    tr.severity = "critical" if findings > 0 else "none"
    return tr


def parse_pip_audit(path: Path, *, exit_code: Optional[int] = None) -> ParsedToolResult:
    tr = ParsedToolResult("pip-audit", parser="pip_audit")
    content = safe_read(path)
    tr.exit_code = exit_code if exit_code is not None else read_exit_code(path)
    if content is None:
        tr.status = ToolStatus.NOT_RUN.value
        return tr
    if _note_unavailable(content):
        tr.status = ToolStatus.NOT_AVAILABLE.value
        tr.severity = "info"
        return tr
    if _note_skipped(content):
        tr.status = ToolStatus.SKIPPED.value
        tr.severity = "info"
        return tr
    lowered = content.lower()
    if "connection" in lowered and ("error" in lowered or "failed" in lowered or "timeout" in lowered):
        if extract_json_object(content) is None:
            tr.status = ToolStatus.EXECUTION_ERROR.value
            tr.severity = "high"
            tr.error = "Error de red/resolución en pip-audit (no equivale a cero vulnerabilidades)."
            return tr
    if "No known vulnerabilities found" in content:
        tr.status = ToolStatus.OK.value
        tr.metrics["total"] = 0
        return tr
    data = extract_json_object(content)
    if data is None:
        if tr.exit_code not in (None, 0, 1):
            tr.status = ToolStatus.EXECUTION_ERROR.value
            tr.error = f"pip-audit exit {tr.exit_code} sin JSON"
            tr.severity = "high"
            return tr
        tr.status = ToolStatus.PARSE_ERROR.value
        tr.severity = "low"
        tr.error = "JSON inválido en pip-audit."
        return tr
    # pip-audit JSON shapes: {"dependencies":[{"vulns":[...]}]} or {"vulnerabilities":[...]}
    vulns = data.get("vulnerabilities")
    if isinstance(vulns, list):
        total = len(vulns)
    else:
        total = 0
        for dep in data.get("dependencies", []) or []:
            total += len(dep.get("vulns") or dep.get("vulnerabilities") or [])
    tr.metrics["total"] = total
    tr.status = ToolStatus.FINDINGS.value if total > 0 else ToolStatus.OK.value
    tr.severity = "medium" if total > 0 else "none"
    return tr


def _pytest_counts(content: str) -> dict[str, int]:
    """Extract pytest summary counts from flexible footer formats."""
    counts: dict[str, int] = {}
    # Prefer the short summary line near the end.
    tail = content[-4000:] if len(content) > 4000 else content
    patterns = {
        "passed": r"(\d+)\s+passed",
        "failed": r"(\d+)\s+failed",
        "skipped": r"(\d+)\s+skipped",
        "errors": r"(\d+)\s+errors?",
        "xfailed": r"(\d+)\s+xfailed",
        "xpassed": r"(\d+)\s+xpassed",
    }
    for key, rgx in patterns.items():
        matches = list(re.finditer(rgx, tail, flags=re.IGNORECASE))
        if matches:
            counts[key] = int(matches[-1].group(1))
    m_col = re.search(r"collected\s+(\d+)\s+items?", content, flags=re.IGNORECASE)
    if m_col:
        counts["collected"] = int(m_col.group(1))
    return counts


def parse_pytest(path: Path, *, exit_code: Optional[int] = None) -> ParsedToolResult:
    tr = ParsedToolResult("Pytest", parser="pytest")
    content = safe_read(path)
    tr.exit_code = exit_code if exit_code is not None else read_exit_code(path)
    if content is None:
        tr.status = ToolStatus.NOT_RUN.value
        return tr
    if _note_unavailable(content):
        tr.status = ToolStatus.NOT_AVAILABLE.value
        tr.severity = "info"
        return tr
    if _note_skipped(content):
        tr.status = ToolStatus.SKIPPED.value
        tr.severity = "info"
        return tr
    if "Interrupted:" in content or "INTERNALERROR" in content:
        tr.status = ToolStatus.EXECUTION_ERROR.value
        tr.severity = "critical"
        tr.error = "Pytest interrupted or internal error."
        counts = _pytest_counts(content)
        tr.metrics.update(counts)
        return tr
    if re.search(r"ERROR collecting|ImportError while importing", content):
        tr.status = ToolStatus.EXECUTION_ERROR.value
        tr.severity = "critical"
        tr.error = "Error de colección/importación."
        counts = _pytest_counts(content)
        tr.metrics.update(counts)
        return tr
    counts = _pytest_counts(content)
    if not counts and not content.strip():
        tr.status = ToolStatus.EXECUTION_ERROR.value
        tr.error = "Salida vacía."
        tr.severity = "high"
        return tr
    if not counts:
        if tr.exit_code is not None and tr.exit_code not in (0, 1):
            tr.status = ToolStatus.EXECUTION_ERROR.value
            tr.error = f"pytest exit {tr.exit_code} sin resumen"
            tr.severity = "high"
            return tr
        tr.status = ToolStatus.PARSE_ERROR.value
        tr.severity = "medium"
        tr.error = "No se pudo parsear resumen de Pytest."
        return tr
    tr.metrics.update(counts)
    failed = counts.get("failed", 0) + counts.get("errors", 0)
    tr.status = ToolStatus.FINDINGS.value if failed > 0 else ToolStatus.OK.value
    tr.severity = "critical" if failed > 0 else "none"
    return tr


def parse_typescript(path: Path, *, exit_code: Optional[int] = None) -> ParsedToolResult:
    """Parse `tsc --noEmit` / npm run typecheck output without false positives."""
    tr = ParsedToolResult("Typecheck", parser="typescript")
    content = safe_read(path)
    tr.exit_code = exit_code if exit_code is not None else read_exit_code(path)
    if content is None:
        tr.status = ToolStatus.NOT_RUN.value
        return tr
    if _note_unavailable(content) or "no se encontro script" in content.lower():
        if "no se encontro script" in content.lower():
            tr.status = ToolStatus.SKIPPED.value
        else:
            tr.status = ToolStatus.NOT_AVAILABLE.value
        tr.severity = "info"
        return tr
    if _note_skipped(content):
        tr.status = ToolStatus.SKIPPED.value
        tr.severity = "info"
        return tr
    # Prefer official summary.
    found = re.search(r"Found (\d+) errors?(?:\s+in\s+(\d+) files?)?", content)
    if found:
        errs = int(found.group(1))
        tr.metrics["ts_errors"] = errs
        if found.group(2):
            tr.metrics["files"] = int(found.group(2))
        tr.status = ToolStatus.FINDINGS.value if errs > 0 else ToolStatus.OK.value
        tr.severity = "high" if errs > 0 else "none"
        return tr
    # Exit 0 wins over noisy text that happens to contain "error TS".
    if tr.exit_code == 0:
        tr.status = ToolStatus.OK.value
        tr.metrics["ts_errors"] = 0
        return tr
    # Count only diagnostic lines: path(line,col): error TS####:
    diag = re.findall(r"error TS\d+:", content)
    # Also accept "error TS####: message" without path in some versions.
    if tr.exit_code is not None and tr.exit_code not in (0, 1, 2):
        # tsc typically exits 1/2 on type errors; other codes → execution.
        if "Cannot find module" in content or "ENOENT" in content or "npm ERR" in content:
            tr.status = ToolStatus.EXECUTION_ERROR.value
            tr.error = "Fallo de ejecución del typecheck (tooling/deps)."
            tr.severity = "high"
            return tr
    if diag:
        tr.metrics["ts_errors"] = len(diag)
        tr.status = ToolStatus.FINDINGS.value
        tr.severity = "high"
        return tr
    if tr.exit_code in (1, 2):
        tr.status = ToolStatus.PARSE_ERROR.value
        tr.error = "Typecheck falló sin resumen parseable."
        tr.severity = "medium"
        return tr
    if tr.exit_code is None:
        # No sidecar — only declare OK if clearly clean.
        if "error TS" not in content and "Found " not in content:
            tr.status = ToolStatus.OK.value
            tr.metrics["ts_errors"] = 0
            return tr
        tr.status = ToolStatus.PARSE_ERROR.value
        tr.error = "Sin exit code ni resumen TypeScript confiable."
        tr.severity = "low"
        return tr
    tr.status = ToolStatus.OK.value
    tr.metrics["ts_errors"] = 0
    return tr


def parse_eslint(path: Path, *, exit_code: Optional[int] = None) -> ParsedToolResult:
    tr = ParsedToolResult("ESLint", parser="eslint")
    content = safe_read(path)
    tr.exit_code = exit_code if exit_code is not None else read_exit_code(path)
    if content is None:
        tr.status = ToolStatus.NOT_RUN.value
        return tr
    if "no se encontro script 'lint'" in content.lower():
        tr.status = ToolStatus.SKIPPED.value
        tr.severity = "medium"
        return tr
    if _note_unavailable(content):
        tr.status = ToolStatus.NOT_AVAILABLE.value
        tr.severity = "info"
        return tr
    # JSON format
    data = extract_json_object(content)
    if isinstance(data, list):
        errors = warnings = 0
        for file_res in data:
            errors += int(file_res.get("errorCount", 0) or 0)
            warnings += int(file_res.get("warningCount", 0) or 0)
        total = errors + warnings
        tr.metrics.update({"problems": total, "errors": errors, "warnings": warnings})
        tr.status = ToolStatus.FINDINGS.value if total > 0 else ToolStatus.OK.value
        tr.severity = "high" if errors > 0 else ("medium" if warnings > 0 else "none")
        return tr
    m = re.search(r"✖\s+(\d+) problems? \((\d+) errors?, (\d+) warnings?\)", content)
    if m:
        total, errors, warnings = map(int, m.groups())
        tr.metrics.update({"problems": total, "errors": errors, "warnings": warnings})
        tr.status = ToolStatus.FINDINGS.value if total > 0 else ToolStatus.OK.value
        tr.severity = "high" if errors > 0 else ("medium" if warnings > 0 else "none")
        return tr
    if tr.exit_code == 0 or re.search(r"^\s*$", content) or "No ESLint warnings or errors" in content:
        tr.status = ToolStatus.OK.value
        tr.metrics.update({"problems": 0, "errors": 0, "warnings": 0})
        return tr
    if tr.exit_code is not None and tr.exit_code not in (0, 1):
        tr.status = ToolStatus.EXECUTION_ERROR.value
        tr.error = f"ESLint exit {tr.exit_code}"
        tr.severity = "high"
        return tr
    tr.status = ToolStatus.PARSE_ERROR.value
    tr.severity = "low"
    tr.error = "No se pudo extraer resumen ESLint."
    return tr


def parse_vitest(path: Path, *, exit_code: Optional[int] = None) -> ParsedToolResult:
    tr = ParsedToolResult("Vitest", parser="vitest")
    content = safe_read(path)
    tr.exit_code = exit_code if exit_code is not None else read_exit_code(path)
    if content is None:
        tr.status = ToolStatus.NOT_RUN.value
        return tr
    if _note_unavailable(content) or _note_skipped(content):
        tr.status = (
            ToolStatus.NOT_AVAILABLE.value if _note_unavailable(content) else ToolStatus.SKIPPED.value
        )
        tr.severity = "info"
        return tr
    if "ERR_" in content and "Test Files" not in content and tr.exit_code not in (0, 1):
        tr.status = ToolStatus.EXECUTION_ERROR.value
        tr.error = "Vitest no inició correctamente."
        tr.severity = "critical"
        return tr
    # Flexible patterns
    m_files = re.search(
        r"Test Files\s+(?:(\d+) failed\s*\|\s*)?(\d+) passed(?:\s*\|\s*(\d+) skipped)?\s*\((\d+)\)",
        content,
    )
    m_tests = re.search(
        r"Tests\s+(?:(\d+) failed\s*\|\s*)?(\d+) passed(?:\s*\|\s*(\d+) skipped)?\s*\((\d+)\)",
        content,
    )
    # Alternate: all failed
    if not m_tests:
        m_tests_alt = re.search(r"Tests\s+(\d+) failed\s*\((\d+)\)", content)
        if m_tests_alt:
            tr.metrics["failed_tests"] = int(m_tests_alt.group(1))
            tr.metrics["total_tests"] = int(m_tests_alt.group(2))
            tr.metrics["passed_tests"] = 0
    if m_files:
        failed_f = int(m_files.group(1) or 0)
        tr.metrics["failed_files"] = failed_f
        tr.metrics["passed_files"] = int(m_files.group(2))
        tr.metrics["total_files"] = int(m_files.group(4))
    if m_tests:
        tr.metrics["failed_tests"] = int(m_tests.group(1) or 0)
        tr.metrics["passed_tests"] = int(m_tests.group(2))
        tr.metrics["total_tests"] = int(m_tests.group(4))
        if m_tests.group(3):
            tr.metrics["skipped_tests"] = int(m_tests.group(3))
    if "failed_tests" not in tr.metrics and "passed_tests" not in tr.metrics:
        if tr.exit_code == 0:
            # Don't invent OK without evidence — PARSE_ERROR if empty, else try "Tests  N passed"
            m_ok = re.search(r"Tests\s+(\d+)\s+passed", content)
            if m_ok:
                tr.metrics["passed_tests"] = int(m_ok.group(1))
                tr.metrics["failed_tests"] = 0
                tr.metrics["total_tests"] = int(m_ok.group(1))
            else:
                tr.status = ToolStatus.PARSE_ERROR.value
                tr.error = "Vitest sin resumen parseable (no asumir OK)."
                tr.severity = "medium"
                return tr
        elif tr.exit_code is None:
            tr.status = ToolStatus.PARSE_ERROR.value
            tr.error = "Vitest sin resumen ni exit code."
            tr.severity = "medium"
            return tr
        else:
            tr.status = ToolStatus.EXECUTION_ERROR.value
            tr.error = f"Vitest exit {tr.exit_code} sin resumen."
            tr.severity = "critical"
            return tr
    failed = tr.metrics.get("failed_tests", 0)
    tr.status = ToolStatus.FINDINGS.value if failed > 0 else ToolStatus.OK.value
    tr.severity = "critical" if failed > 0 else "none"
    return tr


def parse_jest(path: Path, *, exit_code: Optional[int] = None) -> ParsedToolResult:
    tr = ParsedToolResult("Jest", parser="jest")
    content = safe_read(path)
    tr.exit_code = exit_code if exit_code is not None else read_exit_code(path)
    if content is None:
        tr.status = ToolStatus.NOT_RUN.value
        return tr
    if _note_unavailable(content) or _note_skipped(content):
        tr.status = (
            ToolStatus.NOT_AVAILABLE.value if _note_unavailable(content) else ToolStatus.SKIPPED.value
        )
        tr.severity = "info"
        return tr
    # Jest may run multiple configs in one log (core + services + integration).
    # Sum every "Tests:" summary line when several are present.
    test_lines = re.findall(
        r"Tests:\s+(?:(\d+) failed,\s*)?(?:(\d+) skipped,\s*)?(?:(\d+) passed,\s*)?(\d+) total",
        content,
    )
    suite_lines = re.findall(
        r"Test Suites:\s+(?:(\d+) failed,\s*)?(?:(\d+) skipped,\s*)?(?:(\d+) passed,\s*)?(\d+) total",
        content,
    )
    if test_lines:
        failed = skipped = passed = total = 0
        for f, s, p, t in test_lines:
            failed += int(f or 0)
            skipped += int(s or 0)
            passed += int(p or 0)
            total += int(t or 0)
        tr.metrics["failed"] = failed
        tr.metrics["skipped"] = skipped
        tr.metrics["passed"] = passed
        tr.metrics["total"] = total
    if suite_lines:
        failed_s = passed_s = total_s = 0
        for f, _s, p, t in suite_lines:
            failed_s += int(f or 0)
            passed_s += int(p or 0)
            total_s += int(t or 0)
        tr.metrics["failed_suites"] = failed_s
        tr.metrics["passed_suites"] = passed_s
        tr.metrics["total_suites"] = total_s
    if "failed" not in tr.metrics:
        if tr.exit_code == 0 and re.search(r"Test Suites:.+passed", content):
            # Fallback loose
            m2 = re.search(r"Tests:\s+(\d+) passed,\s+(\d+) total", content)
            if m2:
                tr.metrics["passed"] = int(m2.group(1))
                tr.metrics["total"] = int(m2.group(2))
                tr.metrics["failed"] = 0
            else:
                tr.status = ToolStatus.PARSE_ERROR.value
                tr.error = "Jest sin resumen parseable."
                tr.severity = "medium"
                return tr
        elif tr.exit_code not in (None, 0, 1):
            tr.status = ToolStatus.EXECUTION_ERROR.value
            tr.error = f"Jest exit {tr.exit_code}"
            tr.severity = "critical"
            return tr
        else:
            tr.status = ToolStatus.PARSE_ERROR.value
            tr.error = "Jest sin resumen parseable."
            tr.severity = "medium"
            return tr
    failed = tr.metrics.get("failed", 0)
    tr.status = ToolStatus.FINDINGS.value if failed > 0 else ToolStatus.OK.value
    tr.severity = "critical" if failed > 0 else "none"
    return tr


def parse_npm_audit(path: Path, *, exit_code: Optional[int] = None) -> ParsedToolResult:
    tr = ParsedToolResult("npm audit", parser="npm_audit")
    content = safe_read(path)
    tr.exit_code = exit_code if exit_code is not None else read_exit_code(path)
    if content is None:
        tr.status = ToolStatus.NOT_RUN.value
        return tr
    if _note_unavailable(content) or _note_skipped(content):
        tr.status = (
            ToolStatus.NOT_AVAILABLE.value if _note_unavailable(content) else ToolStatus.SKIPPED.value
        )
        tr.severity = "info"
        return tr
    lowered = content.lower()
    if "enotfound" in lowered or "network" in lowered or "fetch failed" in lowered:
        if extract_json_object(content) is None:
            tr.status = ToolStatus.EXECUTION_ERROR.value
            tr.error = "Error de red en npm audit (no equivale a cero vulnerabilidades)."
            tr.severity = "high"
            return tr
    data = extract_json_object(content)
    if data is None:
        tr.status = ToolStatus.PARSE_ERROR.value
        tr.severity = "medium"
        tr.error = "JSON inválido en npm audit."
        return tr
    if data.get("error"):
        tr.status = ToolStatus.EXECUTION_ERROR.value
        tr.error = str(data.get("error"))
        tr.severity = "high"
        return tr
    vul = data.get("metadata", {}).get("vulnerabilities", {}) or {}
    for key in ("critical", "high", "moderate", "low", "info", "total"):
        tr.metrics[key] = int(vul.get(key, 0) or 0)
    total = tr.metrics.get("total", 0)
    tr.status = ToolStatus.FINDINGS.value if total > 0 else ToolStatus.OK.value
    if tr.metrics.get("critical", 0) > 0 or tr.metrics.get("high", 0) > 0:
        tr.severity = "high"
    elif tr.metrics.get("moderate", 0) > 0:
        tr.severity = "medium"
    elif tr.metrics.get("low", 0) > 0:
        tr.severity = "low"
    else:
        tr.severity = "none"
    return tr
