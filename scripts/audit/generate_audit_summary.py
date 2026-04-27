#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


SEVERITY_ORDER = {
    "none": 0,
    "info": 1,
    "low": 2,
    "medium": 3,
    "high": 4,
    "critical": 5,
}


def max_severity(items: List[str]) -> str:
    if not items:
        return "none"
    return max(items, key=lambda s: SEVERITY_ORDER.get(s, 0))


def safe_read(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def extract_json_object(text: str) -> Optional[dict]:
    # Handles reports prefixed with warnings before JSON starts.
    idx = text.find("{")
    if idx < 0:
        return None
    candidate = text[idx:]
    try:
        return json.loads(candidate)
    except Exception:
        return None


@dataclass
class ToolResult:
    name: str
    report: str
    status: str = "NOT_RUN"
    severity: str = "none"
    metrics: Dict[str, int] = field(default_factory=dict)
    observation: str = ""

    def metrics_text(self) -> str:
        if not self.metrics:
            return "-"
        parts = [f"{k}={v}" for k, v in self.metrics.items()]
        return ", ".join(parts)


def status_from_presence(content: Optional[str]) -> str:
    return "NOT_RUN" if content is None else "OK"


def parse_backend_ruff(path: Path) -> ToolResult:
    tr = ToolResult("Ruff", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    m = re.search(r"Found (\d+) errors\.", content)
    fx = re.search(r"\[\*\]\s+(\d+)\s+fixable", content)
    lowered = content.lower()
    if "no instalado" in lowered:
        tr.status = "NOT_RUN"
        tr.severity = "info"
        tr.observation = "Herramienta no instalada en la corrida."
        return tr
    if "no ejecutado" in lowered:
        tr.status = "SKIPPED"
        tr.severity = "info"
        return tr
    if m:
        issues = int(m.group(1))
        tr.metrics["issues"] = issues
        tr.status = "FINDINGS" if issues > 0 else "OK"
        tr.severity = "medium" if issues > 0 else "none"
        if fx:
            tr.metrics["fixable"] = int(fx.group(1))
    elif "no se detecto" in lowered:
        tr.status = "SKIPPED"
        tr.severity = "info"
    else:
        tr.status = "ERROR"
        tr.severity = "low"
        tr.observation = "No se pudo extraer métrica de Ruff."
    return tr


def parse_backend_mypy(path: Path) -> ToolResult:
    tr = ToolResult("Mypy", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    lowered = content.lower()
    if "no instalado" in lowered:
        tr.status = "NOT_RUN"
        tr.severity = "info"
        return tr
    if "no ejecutado" in lowered:
        tr.status = "SKIPPED"
        tr.severity = "info"
        return tr
    if "Success:" in content:
        tr.status = "OK"
        tr.severity = "none"
        return tr
    m = re.search(r"Found (\d+) errors in (\d+) files", content)
    if m:
        errs, files = int(m.group(1)), int(m.group(2))
        tr.metrics["errors"] = errs
        tr.metrics["files"] = files
        tr.status = "FINDINGS" if errs > 0 else "OK"
        tr.severity = "high" if errs > 0 else "none"
    elif "error:" in content:
        tr.status = "FINDINGS"
        tr.severity = "high"
    else:
        tr.status = "ERROR"
        tr.severity = "low"
        tr.observation = "No se pudo parsear salida de Mypy."
    return tr


def parse_backend_bandit(path: Path) -> ToolResult:
    tr = ToolResult("Bandit", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    lowered = content.lower()
    if "no instalado" in lowered:
        tr.status = "NOT_RUN"
        tr.severity = "info"
        return tr
    if "no ejecutado" in lowered:
        tr.status = "SKIPPED"
        tr.severity = "info"
        return tr
    data = extract_json_object(content)
    if data is None:
        tr.status = "ERROR"
        tr.severity = "high"
        tr.observation = "JSON inválido o no parseable."
        return tr
    results = data.get("results", [])
    sev_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in results:
        sev = str(r.get("issue_severity", "")).upper()
        if sev in sev_counts:
            sev_counts[sev] += 1
    total = sum(sev_counts.values())
    tr.metrics.update(
        {
            "total": total,
            "high": sev_counts["HIGH"],
            "medium": sev_counts["MEDIUM"],
            "low": sev_counts["LOW"],
        }
    )
    tr.status = "FINDINGS" if total > 0 else "OK"
    tr.severity = (
        "high"
        if sev_counts["HIGH"] > 0
        else ("medium" if sev_counts["MEDIUM"] > 0 else ("low" if total > 0 else "none"))
    )
    return tr


def parse_backend_pip_audit(path: Path) -> ToolResult:
    tr = ToolResult("pip-audit", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    lowered = content.lower()
    if "no instalado" in lowered:
        tr.status = "NOT_RUN"
        tr.severity = "info"
        return tr
    if "no ejecutado" in lowered:
        tr.status = "SKIPPED"
        tr.severity = "info"
        return tr
    if "No known vulnerabilities found" in content:
        tr.status = "OK"
        tr.severity = "none"
        tr.metrics["total"] = 0
        if "skip_reason" in content:
            tr.observation = "Paquete local no auditable en PyPI."
        return tr
    data = extract_json_object(content)
    if data is None:
        tr.status = "ERROR"
        tr.severity = "low"
        return tr
    vulns = data.get("vulnerabilities", [])
    tr.metrics["total"] = len(vulns)
    tr.status = "FINDINGS" if vulns else "OK"
    tr.severity = "medium" if vulns else "none"
    return tr


def parse_backend_pytest(path: Path) -> ToolResult:
    tr = ToolResult("Pytest", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    lowered = content.lower()
    if "no instalado" in lowered:
        tr.status = "NOT_RUN"
        tr.severity = "info"
        return tr
    if "no ejecutado" in lowered:
        tr.status = "SKIPPED"
        tr.severity = "info"
        return tr
    m_col = re.search(r"collected (\d+) items", content)
    m_res = re.search(r"(\d+) failed, (\d+) passed, (\d+) skipped", content)
    if m_col:
        tr.metrics["collected"] = int(m_col.group(1))
    if m_res:
        failed, passed, skipped = map(int, m_res.groups())
        tr.metrics["failed"] = failed
        tr.metrics["passed"] = passed
        tr.metrics["skipped"] = skipped
        tr.status = "FINDINGS" if failed > 0 else "OK"
        tr.severity = "critical" if failed > 0 else "none"
    else:
        tr.status = "ERROR"
        tr.severity = "medium"
    return tr


def parse_frontend_eslint(path: Path) -> ToolResult:
    tr = ToolResult("ESLint", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    if "no se encontro script 'lint'" in content.lower():
        tr.status = "SKIPPED"
        tr.severity = "medium"
        tr.observation = "No existe script lint."
        return tr
    m = re.search(r"✖\s+(\d+) problems \((\d+) errors, (\d+) warnings\)", content)
    if m:
        total, errors, warnings = map(int, m.groups())
        tr.metrics.update({"problems": total, "errors": errors, "warnings": warnings})
        tr.status = "FINDINGS" if total > 0 else "OK"
        tr.severity = "high" if errors > 0 else ("medium" if warnings > 0 else "none")
    else:
        tr.status = "ERROR"
        tr.severity = "low"
        tr.observation = "No se pudo extraer resumen ESLint."
    return tr


def parse_frontend_typecheck(path: Path) -> ToolResult:
    tr = ToolResult("Typecheck", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    ts_errors = len(re.findall(r"error TS\d+:", content))
    tr.metrics["ts_errors"] = ts_errors
    tr.status = "FINDINGS" if ts_errors > 0 else "OK"
    tr.severity = "high" if ts_errors > 0 else "none"
    return tr


def parse_frontend_npm_audit(path: Path) -> ToolResult:
    tr = ToolResult("npm audit", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    data = extract_json_object(content)
    if data is None:
        tr.status = "ERROR"
        tr.severity = "medium"
        tr.observation = "JSON inválido en npm audit."
        return tr
    vul = data.get("metadata", {}).get("vulnerabilities", {})
    for key in ("critical", "high", "moderate", "low", "info", "total"):
        tr.metrics[key] = int(vul.get(key, 0))
    total = tr.metrics["total"]
    tr.status = "FINDINGS" if total > 0 else "OK"
    if tr.metrics["critical"] > 0 or tr.metrics["high"] > 0:
        tr.severity = "high"
    elif tr.metrics["moderate"] > 0:
        tr.severity = "medium"
    elif tr.metrics["low"] > 0:
        tr.severity = "low"
    else:
        tr.severity = "none"
    return tr


def parse_frontend_vitest(path: Path) -> ToolResult:
    tr = ToolResult("Vitest", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    m_files = re.search(r"Test Files\s+(\d+) failed \| (\d+) passed \((\d+)\)", content)
    m_tests = re.search(r"Tests\s+(\d+) failed \| (\d+) passed \((\d+)\)", content)
    if m_files:
        tr.metrics["failed_files"] = int(m_files.group(1))
        tr.metrics["passed_files"] = int(m_files.group(2))
        tr.metrics["total_files"] = int(m_files.group(3))
    if m_tests:
        tr.metrics["failed_tests"] = int(m_tests.group(1))
        tr.metrics["passed_tests"] = int(m_tests.group(2))
        tr.metrics["total_tests"] = int(m_tests.group(3))
    failed_tests = tr.metrics.get("failed_tests", 0)
    tr.status = "FINDINGS" if failed_tests > 0 else "OK"
    tr.severity = "critical" if failed_tests > 0 else "none"
    return tr


def parse_metric_md(path: Path, name: str, regex_pairs: List[Tuple[str, str]], default_sev: str) -> ToolResult:
    tr = ToolResult(name, str(path))
    content = safe_read(path)
    if content is None:
        return tr
    found = False
    for key, rgx in regex_pairs:
        m = re.search(rgx, content)
        if m:
            tr.metrics[key] = int(m.group(1))
            found = True
    tr.status = "FINDINGS" if found else "SKIPPED"
    tr.severity = default_sev if found else "info"
    if not found:
        tr.observation = "Sin métricas detectables; posible limitación heurística."
    return tr


def parse_arch_backend_code_smells(path: Path) -> ToolResult:
    tr = ToolResult("Code smells", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    lowered = content.lower()
    if "no instalado" in lowered:
        tr.status = "NOT_RUN"
        tr.severity = "info"
        return tr
    if "no ejecutado" in lowered:
        tr.status = "SKIPPED"
        tr.severity = "info"
        return tr
    keys = {
        "too_many_args": r"too-many-arguments",
        "too_many_branches": r"too-many-branches",
        "too_many_returns": r"too-many-return-statements",
        "broad_exception": r"broad-exception",
        "unused_import": r"unused-import",
    }
    for metric, rgx in keys.items():
        tr.metrics[metric] = len(re.findall(rgx, content, flags=re.IGNORECASE))
    total = sum(tr.metrics.values())
    tr.metrics["signals"] = total
    tr.status = "FINDINGS" if total > 0 else "OK"
    tr.severity = "high" if total >= 50 else ("medium" if total > 0 else "none")
    return tr


def parse_arch_backend_complexity(path: Path) -> ToolResult:
    tr = ToolResult("Complejidad", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    lowered = content.lower()
    if "no instalado" in lowered:
        tr.status = "NOT_RUN"
        tr.severity = "info"
        return tr
    if "no ejecutado" in lowered:
        tr.status = "SKIPPED"
        tr.severity = "info"
        return tr
    tr.metrics["grade_c"] = len(re.findall(r"\s-\sC\s\(", content))
    tr.metrics["grade_d"] = len(re.findall(r"\s-\sD\s\(", content))
    tr.metrics["grade_e"] = len(re.findall(r"\s-\sE\s\(", content))
    tr.metrics["grade_f"] = len(re.findall(r"\s-\sF\s\(", content))
    high_risk = tr.metrics["grade_d"] + tr.metrics["grade_e"] + tr.metrics["grade_f"]
    tr.status = "FINDINGS" if (high_risk + tr.metrics["grade_c"]) > 0 else "OK"
    tr.severity = "high" if high_risk > 0 else ("medium" if tr.metrics["grade_c"] > 0 else "none")
    return tr


def parse_arch_backend_imports(path: Path) -> ToolResult:
    tr = ToolResult("Límites de imports", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    lowered = content.lower()
    if "no instalado" in lowered:
        tr.status = "NOT_RUN"
        tr.severity = "info"
        return tr
    if "no ejecutado" in lowered:
        tr.status = "SKIPPED"
        tr.severity = "info"
        return tr
    m_fail = re.search(r"FAIL=(\d+)", content)
    m_rev = re.search(r"REVIEW=(\d+)", content)
    fail = int(m_fail.group(1)) if m_fail else len(re.findall(r": FAIL", content))
    rev = int(m_rev.group(1)) if m_rev else len(re.findall(r": REVIEW", content))
    tr.metrics["fail"] = fail
    tr.metrics["review"] = rev
    tr.status = "FINDINGS" if (fail + rev) > 0 else "OK"
    tr.severity = "high" if fail > 0 else ("medium" if rev > 0 else "none")
    return tr


def parse_arch_backend_solid(path: Path) -> ToolResult:
    tr = ToolResult("SOLID/GRASP", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    lowered = content.lower()
    if "no instalado" in lowered:
        tr.status = "NOT_RUN"
        tr.severity = "info"
        return tr
    if "no ejecutado" in lowered:
        tr.status = "SKIPPED"
        tr.severity = "info"
        return tr
    findings = len(re.findall(r"hallazgos iniciales|señales", content, flags=re.IGNORECASE))
    tr.metrics["signals"] = findings
    tr.status = "FINDINGS" if findings > 0 else "OK"
    tr.severity = "medium" if findings > 0 else "none"
    return tr


def parse_arch_frontend_code_smells(path: Path) -> ToolResult:
    tr = ToolResult("Code smells", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    m = re.search(r"✖\s+(\d+) problems \((\d+) errors, (\d+) warnings\)", content)
    if m:
        total, errors, warnings = map(int, m.groups())
        tr.metrics.update({"problems": total, "errors": errors, "warnings": warnings})
        tr.status = "FINDINGS" if total > 0 else "OK"
        tr.severity = "high" if errors > 0 else ("medium" if warnings > 0 else "none")
    else:
        tr.status = "FINDINGS" if "useEffect_usages_approx" in content else "SKIPPED"
        tr.severity = "medium" if tr.status == "FINDINGS" else "info"
    return tr


def parse_arch_frontend_complexity(path: Path) -> ToolResult:
    tr = ToolResult("Complejidad", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    for key, rgx in [
        ("files_scanned", r"files_scanned: (\d+)"),
        ("functions_approx", r"functions_approx: (\d+)"),
        ("conditional_tokens", r"conditional_tokens_approx: (\d+)"),
    ]:
        m = re.search(rgx, content)
        if m:
            tr.metrics[key] = int(m.group(1))
    gt_300 = len(re.findall(r"^- .*: \d+$", content, flags=re.MULTILINE))
    gt_1000 = len(re.findall(r": 1\d{3,}|: [2-9]\d{3,}", content))
    tr.metrics["files_gt_300"] = gt_300
    tr.metrics["files_gt_1000"] = gt_1000
    tr.status = "FINDINGS" if (gt_300 + gt_1000) > 0 else "OK"
    tr.severity = "high" if gt_1000 > 0 else ("medium" if gt_300 > 0 else "none")
    return tr


def parse_arch_frontend_imports(path: Path) -> ToolResult:
    tr = ToolResult("Límites de imports", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    sig = len(re.findall(r"R1 components->api/fetch|R4 ui-business-logic-suspect", content))
    tr.metrics["signals"] = sig
    tr.status = "FINDINGS" if sig > 0 else "OK"
    tr.severity = "high" if sig >= 30 else ("medium" if sig > 0 else "none")
    return tr


def parse_arch_frontend_dup(path: Path) -> ToolResult:
    tr = ToolResult("Duplicación", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    if "jscpd no instalado" in content.lower():
        tr.status = "SKIPPED"
        tr.severity = "info"
        tr.observation = "jscpd no instalado; fallback heurístico."
    else:
        tr.status = "FINDINGS"
        tr.severity = "medium"
    return tr


def parse_arch_frontend_dead(path: Path) -> ToolResult:
    tr = ToolResult("Código muerto", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    sig = len(re.findall(r"^src/.*:\d+ - ", content, flags=re.MULTILINE))
    tr.metrics["signals"] = sig
    tr.status = "FINDINGS" if sig > 0 else "OK"
    tr.severity = "medium" if sig > 50 else ("low" if sig > 0 else "none")
    return tr


def parse_arch_frontend_solid(path: Path) -> ToolResult:
    tr = ToolResult("SOLID/React", str(path))
    content = safe_read(path)
    if content is None:
        return tr
    sig = len(re.findall(r"Señales de|Hallazgos iniciales|hallazgos", content, flags=re.IGNORECASE))
    tr.metrics["signals"] = sig
    tr.status = "FINDINGS" if sig > 0 else "OK"
    tr.severity = "medium" if sig > 0 else "none"
    return tr


def compute_area_status(tools: List[ToolResult]) -> str:
    statuses = [t.status for t in tools]
    if any(s == "ERROR" for s in statuses):
        return "ERROR"
    if any(s == "FINDINGS" for s in statuses):
        return "FINDINGS"
    if all(s in {"NOT_RUN", "SKIPPED"} for s in statuses):
        return "NOT_RUN"
    if all(s == "OK" for s in statuses):
        return "OK"
    return "FINDINGS"


def area_observation(area: str, tools: List[ToolResult]) -> str:
    if area == "backend":
        failed = next((t.metrics.get("failed", 0) for t in tools if t.name == "Pytest"), 0)
        return f"Tests fallidos backend={failed}" if failed else "Sin fallos críticos detectados"
    if area == "frontend":
        failed = next((t.metrics.get("failed_tests", 0) for t in tools if t.name == "Vitest"), 0)
        return f"Tests fallidos frontend={failed}" if failed else "Sin fallos de tests"
    if area == "backend_architecture":
        fail = next((t.metrics.get("fail", 0) for t in tools if t.name == "Límites de imports"), 0)
        return f"Boundary FAIL={fail}" if fail else "Sin FAIL de boundaries"
    if area == "frontend_architecture":
        sig = next((t.metrics.get("signals", 0) for t in tools if t.name == "Límites de imports"), 0)
        return f"Import signals={sig}" if sig else "Sin señales fuertes de acoplamiento"
    return "-"


def tool_table_md(title: str, headers: List[str], rows: List[List[str]]) -> str:
    out = [f"## {title}", "", f"| {' | '.join(headers)} |", f"|{'|'.join(['---']*len(headers))}|"]
    for row in rows:
        out.append(f"| {' | '.join(row)} |")
    out.append("")
    return "\n".join(out)


def build_summary_markdown(
    generated_at: str,
    overall_status: str,
    max_sev: str,
    areas: Dict[str, List[ToolResult]],
) -> str:
    lines: List[str] = []
    lines.append("# Resumen automático de auditoría")
    lines.append("")
    lines.append(f"Fecha: {generated_at}")
    lines.append(f"Estado general: {overall_status.upper()}")
    lines.append(f"Severidad máxima: {max_sev}")
    lines.append("")
    lines.append("## Estado general")
    lines.append("")
    lines.append("| Área | Estado | Severidad máxima | Observación |")
    lines.append("|---|---|---|---|")
    for area_key, label in [
        ("backend", "Backend"),
        ("frontend", "Frontend"),
        ("backend_architecture", "Arquitectura backend"),
        ("frontend_architecture", "Arquitectura frontend"),
    ]:
        tools = areas[area_key]
        lines.append(
            f"| {label} | {compute_area_status(tools)} | {max_severity([t.severity for t in tools])} | {area_observation(area_key, tools)} |"
        )
    lines.append("")

    for area_key, title in [
        ("backend", "Backend"),
        ("frontend", "Frontend"),
        ("backend_architecture", "Arquitectura backend"),
        ("frontend_architecture", "Arquitectura frontend"),
    ]:
        tools = areas[area_key]
        headers = ["Herramienta", "Estado", "Severidad", "Métricas", "Reporte"]
        if "Arquitectura" in title:
            headers[0] = "Auditoría"
        rows = [[t.name, t.status, t.severity, t.metrics_text(), t.report] for t in tools]
        lines.append(tool_table_md(title, headers, rows))

    highlights: List[str] = []
    b_pytest = next((t for t in areas["backend"] if t.name == "Pytest"), None)
    if b_pytest and b_pytest.metrics.get("failed", 0) > 0:
        highlights.append(f"Backend pytest reporta {b_pytest.metrics['failed']} tests fallidos.")
    f_vitest = next((t for t in areas["frontend"] if t.name == "Vitest"), None)
    if f_vitest and f_vitest.metrics.get("failed_tests", 0) > 0:
        highlights.append(f"Frontend vitest reporta {f_vitest.metrics['failed_tests']} tests fallidos.")
    b_bandit = next((t for t in areas["backend"] if t.name == "Bandit"), None)
    if b_bandit:
        highlights.append(
            f"Bandit: total={b_bandit.metrics.get('total', 0)}, high={b_bandit.metrics.get('high', 0)}, medium={b_bandit.metrics.get('medium', 0)}."
        )
    f_npm = next((t for t in areas["frontend"] if t.name == "npm audit"), None)
    if f_npm and f_npm.metrics.get("total", 0) > 0:
        highlights.append(
            f"npm audit frontend: moderate={f_npm.metrics.get('moderate', 0)}, high={f_npm.metrics.get('high', 0)}, critical={f_npm.metrics.get('critical', 0)}."
        )
    b_mypy = next((t for t in areas["backend"] if t.name == "Mypy"), None)
    if b_mypy and b_mypy.metrics.get("errors", 0) > 0:
        highlights.append(f"Mypy backend detecta {b_mypy.metrics['errors']} errores en {b_mypy.metrics.get('files', 0)} archivos.")
    fb_c = next((t for t in areas["frontend_architecture"] if t.name == "Complejidad"), None)
    if fb_c:
        highlights.append(
            f"Complejidad frontend: files>{300}={fb_c.metrics.get('files_gt_300', 0)}, files>{1000}={fb_c.metrics.get('files_gt_1000', 0)}."
        )
    bb_i = next((t for t in areas["backend_architecture"] if t.name == "Límites de imports"), None)
    if bb_i:
        highlights.append(
            f"Boundaries backend: fail={bb_i.metrics.get('fail', 0)}, review={bb_i.metrics.get('review', 0)}."
        )
    ff_i = next((t for t in areas["frontend_architecture"] if t.name == "Límites de imports"), None)
    if ff_i and ff_i.metrics.get("signals", 0) > 0:
        highlights.append(f"Boundaries frontend: señales heurísticas={ff_i.metrics['signals']}.")
    ff_dead = next((t for t in areas["frontend_architecture"] if t.name == "Código muerto"), None)
    if ff_dead and ff_dead.metrics.get("signals", 0) > 0:
        highlights.append(f"Código muerto frontend: señales={ff_dead.metrics['signals']} (requiere validación manual).")
    ff_dup = next((t for t in areas["frontend_architecture"] if t.name == "Duplicación"), None)
    if ff_dup and ff_dup.status in {"SKIPPED", "NOT_RUN"}:
        highlights.append("Duplicación frontend no cuantificada formalmente (jscpd no disponible).")
    useff = next((t for t in areas["frontend"] if t.name == "useEffect audit"), None)
    if useff:
        highlights.append(
            f"useEffect audit: usos={useff.metrics.get('uses', 0)}, archivos={useff.metrics.get('files', 0)}; revisar posibles falsos negativos."
        )
    errh = next((t for t in areas["frontend"] if t.name == "Error handling audit"), None)
    if errh:
        highlights.append(
            f"Error handling audit: archivos={errh.metrics.get('files', 0)}, try={errh.metrics.get('try_blocks', 0)}, catch={errh.metrics.get('catch_blocks', 0)}."
        )
    ruff = next((t for t in areas["backend"] if t.name == "Ruff"), None)
    if ruff and ruff.metrics.get("issues", 0) > 0:
        highlights.append(
            f"Ruff backend: issues={ruff.metrics['issues']}, fixable={ruff.metrics.get('fixable', 0)}."
        )

    lines.append("## Hallazgos principales automáticos")
    lines.append("")
    for h in highlights[:20]:
        lines.append(f"- {h}")
    lines.append("")
    lines.append("## Recomendación automática de prioridad")
    lines.append("")
    lines.append("1. Tests críticos")
    lines.append("2. Seguridad/dependencias")
    lines.append("3. Tipado")
    lines.append("4. Arquitectura")
    lines.append("5. Code smells")
    lines.append("6. Limpieza/ruido")
    lines.append("")
    lines.append("## Limitaciones")
    lines.append("")
    lines.append("- Esta consolidación es automática y puede requerir revisión humana.")
    lines.append("- Los principios SOLID/GRASP/React se interpretan como señales heurísticas.")
    lines.append("- Algunos reportes pueden depender de herramientas instaladas localmente.")
    lines.append("- No implica corrección automática.")
    lines.append("")
    return "\n".join(lines)


def update_audit_report_with_autosection(audit_report: Path, summary_md: str, generated_at: str) -> None:
    if not audit_report.exists():
        return
    start = "<!-- AUTO-AUDIT-SUMMARY:START -->"
    end = "<!-- AUTO-AUDIT-SUMMARY:END -->"
    block = (
        f"{start}\n"
        f"## Consolidación automática reproducible\n\n"
        f"- Generado: {generated_at}\n"
        f"- Fuente automática: `audit/audit-summary.md`\n"
        f"- Estado machine-readable: `audit/audit-status.json`\n\n"
        f"Resumen breve:\n\n"
        f"{summary_md.split('## Estado general')[0].strip()}\n"
        f"{end}"
    )
    content = audit_report.read_text(encoding="utf-8", errors="replace")
    if start in content and end in content:
        new_content = re.sub(
            re.escape(start) + r".*?" + re.escape(end),
            block,
            content,
            flags=re.DOTALL,
        )
    else:
        new_content = content.rstrip() + "\n\n" + block + "\n"
    audit_report.write_text(new_content, encoding="utf-8")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    raw = repo_root / "audit" / "raw"
    audit_dir = repo_root / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    backend = [
        parse_backend_ruff(raw / "backend-ruff.txt"),
        parse_backend_mypy(raw / "backend-mypy.txt"),
        parse_backend_bandit(raw / "backend-bandit.json"),
        parse_backend_pip_audit(raw / "backend-pip-audit.json"),
        parse_backend_pytest(raw / "backend-pytest.txt"),
    ]
    frontend = [
        parse_frontend_eslint(raw / "frontend-eslint.txt"),
        parse_frontend_typecheck(raw / "frontend-typecheck.txt"),
        parse_frontend_npm_audit(raw / "frontend-npm-audit.json"),
        parse_frontend_vitest(raw / "frontend-vitest.txt"),
        parse_metric_md(
            raw / "frontend-useeffects-audit.md",
            "useEffect audit",
            [("uses", r"usos de `useEffect`: (\d+)"), ("files", r"archivos con `useEffect`: (\d+)")],
            "medium",
        ),
        parse_metric_md(
            raw / "frontend-error-handling-audit.md",
            "Error handling audit",
            [
                ("files", r"patrones de manejo de errores detectados \(aprox\): (\d+)"),
                ("try_blocks", r"Bloques try detectados \(aprox\): (\d+)"),
                ("catch_blocks", r"Bloques catch detectados \(aprox\): (\d+)"),
            ],
            "medium",
        ),
        parse_metric_md(
            raw / "frontend-reusable-components-audit.md",
            "Reusable components audit",
            [("candidate_files", r"candidatas.*: (\d+)"), ("button_refs", r"Referencias a Button: (\d+)")],
            "medium",
        ),
    ]
    backend_arch = [
        parse_arch_backend_code_smells(raw / "backend-code-smells.txt"),
        parse_arch_backend_complexity(raw / "backend-complexity.txt"),
        parse_arch_backend_imports(raw / "backend-import-boundaries.txt"),
        parse_arch_backend_solid(raw / "backend-solid-grasp-audit.md"),
    ]
    frontend_arch = [
        parse_arch_frontend_code_smells(raw / "frontend-code-smells.txt"),
        parse_arch_frontend_complexity(raw / "frontend-complexity.txt"),
        parse_arch_frontend_imports(raw / "frontend-import-boundaries.txt"),
        parse_arch_frontend_dup(raw / "frontend-duplication.txt"),
        parse_arch_frontend_dead(raw / "frontend-dead-code.txt"),
        parse_arch_frontend_solid(raw / "frontend-solid-react-audit.md"),
    ]

    areas = {
        "backend": backend,
        "frontend": frontend,
        "backend_architecture": backend_arch,
        "frontend_architecture": frontend_arch,
    }

    area_status = {k: compute_area_status(v) for k, v in areas.items()}
    all_sev = [t.severity for vals in areas.values() for t in vals]
    overall_max_sev = max_severity(all_sev)

    if any(s == "ERROR" for s in area_status.values()):
        overall_status = "error"
    elif any(s in {"FINDINGS", "SKIPPED", "NOT_RUN"} for s in area_status.values()):
        overall_status = "findings"
    else:
        overall_status = "ok"

    status_obj = {
        "overall_status": overall_status,
        "max_severity": overall_max_sev,
        "generated_at": generated_at,
        "areas": {},
    }
    for area_key, tools in areas.items():
        status_obj["areas"][area_key] = {
            "status": area_status[area_key],
            "max_severity": max_severity([t.severity for t in tools]),
            "tools": {
                t.name.lower().replace(" ", "_"): {
                    "status": t.status,
                    "severity": t.severity,
                    "metrics": t.metrics,
                    "report": t.report,
                    "observation": t.observation,
                }
                for t in tools
            },
            "highlights": {
                "tool_count": len(tools),
                "findings_count": sum(1 for t in tools if t.status == "FINDINGS"),
                "not_run_count": sum(1 for t in tools if t.status in {"NOT_RUN", "SKIPPED"}),
            },
        }

    summary_md = build_summary_markdown(generated_at, overall_status, overall_max_sev, areas)

    (audit_dir / "audit-summary.md").write_text(summary_md, encoding="utf-8")
    (audit_dir / "audit-status.json").write_text(
        json.dumps(status_obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Optional: append/update clearly marked auto-generated section in manual report.
    update_audit_report_with_autosection(audit_dir / "audit-report.md", summary_md, generated_at)

    print(f"Generated: {audit_dir / 'audit-summary.md'}")
    print(f"Generated: {audit_dir / 'audit-status.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
