# Security Audit Report — dinamic-gemini

- audit_run_id: `20260806T182609Z_8c25dcdee018`
- framework_version: `0.3.0`

## Stack detected

Languages: c(HIGH), cpp(MEDIUM), css(MEDIUM), html(MEDIUM), javascript(HIGH), json(HIGH), kotlin(HIGH), python(HIGH), shell(HIGH), sql(HIGH), toml(MEDIUM), typescript(HIGH), yaml(HIGH)

## SAST

- Selected tools: gitleaks, semgrep, trivy_fs, trivy_config, osv_scanner, npm_audit
- Skipped tools: 4
- Execution summary present: True

## DAST gates

- active_allowed: True
- blockers: none

## Findings (provisional)

Total: 47

- `SAST-001` [LOW/NEEDS_MANUAL_VALIDATION] No HEALTHCHECK defined (source=sast)
- `SAST-002` [LOW/NEEDS_MANUAL_VALIDATION] No HEALTHCHECK defined (source=sast)
- `SAST-003` [HIGH/NEEDS_MANUAL_VALIDATION] Image user should not be 'root' (source=sast)
- `SAST-004` [HIGH/NEEDS_MANUAL_VALIDATION] 'apt-get' missing '-y' to avoid manual input (source=sast)
- `SAST-005` [LOW/NEEDS_MANUAL_VALIDATION] No HEALTHCHECK defined (source=sast)
- `SAST-006` [HIGH/NEEDS_MANUAL_VALIDATION] 'apt-get' missing '--no-install-recommends' (source=sast)
- `SAST-007` [HIGH/NEEDS_MANUAL_VALIDATION] Image user should not be 'root' (source=sast)
- `SAST-008` [LOW/NEEDS_MANUAL_VALIDATION] No HEALTHCHECK defined (source=sast)
- `SAST-009` [HIGH/NEEDS_MANUAL_VALIDATION] Image user should not be 'root' (source=sast)
- `SAST-010` [LOW/NEEDS_MANUAL_VALIDATION] No HEALTHCHECK defined (source=sast)
- `SAST-011` [MEDIUM/LIKELY] React Router: Open redirect via backslash in <Link> and useNavigate (CVE-2025-68470 bypass) (source=sast)
- `SAST-012` [MEDIUM/LIKELY] React Router: Open redirect leading to XSS (source=sast)
- `SAST-013` [MEDIUM/LIKELY] uuid (source=sast)
- `SAST-014` [HIGH/LIKELY] @expo/config (source=sast)
- `SAST-015` [HIGH/LIKELY] @expo/config-plugins (source=sast)
- `SAST-016` [HIGH/LIKELY] @expo/plist (source=sast)
- `SAST-017` [HIGH/LIKELY] @expo/config (source=sast)
- `SAST-018` [HIGH/LIKELY] @xmldom/xmldom (source=sast)
- `SAST-019` [HIGH/LIKELY] @expo/config (source=sast)
- `SAST-020` [MEDIUM/LIKELY] @expo/bunyan (source=sast)
- `SAST-021` [MEDIUM/LIKELY] @react-native-community/cli-doctor (source=sast)
- `SAST-022` [MEDIUM/LIKELY] @react-native-community/cli-platform-android (source=sast)
- `SAST-023` [MEDIUM/LIKELY] @react-native-community/cli-platform-android (source=sast)
- `SAST-024` [MEDIUM/LIKELY] fast-xml-parser (source=sast)
- `SAST-025` [MEDIUM/LIKELY] fast-xml-parser (source=sast)
- `SAST-026` [MEDIUM/LIKELY] @react-native-community/cli-platform-apple (source=sast)
- `SAST-027` [HIGH/LIKELY] xmldom: XML injection via unsafe CDATA serialization allows attacker-controlled markup insertion (source=sast)
- `SAST-028` [MEDIUM/LIKELY] ajv has ReDoS when using `$data` option (source=sast)
- `SAST-029` [HIGH/LIKELY] brace-expansion: DoS via unbounded expansion length causing an out-of-memory process crash (source=sast)
- `SAST-030` [HIGH/LIKELY] tar (source=sast)
- `SAST-031` [HIGH/LIKELY] @expo/cli (source=sast)
- `SAST-032` [HIGH/LIKELY] expo-constants (source=sast)
- `SAST-033` [HIGH/LIKELY] @expo/config (source=sast)
- `SAST-034` [HIGH/LIKELY] expo-dev-launcher (source=sast)
- `SAST-035` [HIGH/LIKELY] ajv (source=sast)
- `SAST-036` [HIGH/LIKELY] @expo/config (source=sast)
- `SAST-037` [MEDIUM/LIKELY] fast-xml-parser XMLBuilder: XML Comment and CDATA Injection via Unescaped Delimiters (source=sast)
- `SAST-038` [HIGH/LIKELY] PostCSS has XSS via Unescaped </style> in its CSS Stringify Output (source=sast)
- `SAST-039` [MEDIUM/LIKELY] @react-native-community/cli (source=sast)
- `SAST-040` [LOW/LIKELY] send vulnerable to template injection that can lead to XSS (source=sast)
- `SAST-041` [CRITICAL/LIKELY] node-tar Vulnerable to Arbitrary File Creation/Overwrite via Hardlink Path Traversal (source=sast)
- `SAST-042` [MEDIUM/LIKELY] uuid: Missing buffer bounds check in v3/v5/v6 when buf is provided (source=sast)
- `SAST-043` [MEDIUM/LIKELY] uuid (source=sast)
- `SAST-044` [LOW/LIKELY] @babel/core: Arbitrary File Read via sourceMappingURL Comment (source=sast)
- `SAST-045` [HIGH/LIKELY] brace-expansion: Large numeric range defeats documented `max` DoS protection (source=sast)
- `SAST-046` [HIGH/LIKELY] lodash vulnerable to Code Injection via `_.template` imports key names (source=sast)
- `SAST-047` [CRITICAL/LIKELY] shell-quote quote() does not escape newlines in object .op values (source=sast)

## Limitations

- Scanner alerts are not auto-confirmed; statuses are provisional.
- CodeQL full pipeline not implemented.
- Complex login flows, Burp, SPA crawling, GraphQL DAST, mobile DAST not implemented.
- Active DAST remains fail-closed and requires per-run confirmation.
- Tools marked not_available were not executed; no invented results.

> Remediation of product code is a separate explicit phase and was not performed.
