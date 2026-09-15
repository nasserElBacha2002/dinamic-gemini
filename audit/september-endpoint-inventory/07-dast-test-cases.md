# 07 — Future DAST test cases (NOT EXECUTED)

### DAST-EP-0013-01
- endpoint: `GET /api/v3/clients/`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0013-02
- endpoint: `GET /api/v3/clients/`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0013-03
- endpoint: `GET /api/v3/clients/`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0014-04
- endpoint: `POST /api/v3/clients/`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0014-05
- endpoint: `POST /api/v3/clients/`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0014-06
- endpoint: `POST /api/v3/clients/`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0015-07
- endpoint: `GET /api/v3/clients/{client_id}`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0015-08
- endpoint: `GET /api/v3/clients/{client_id}`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0015-09
- endpoint: `GET /api/v3/clients/{client_id}`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0016-10
- endpoint: `PATCH /api/v3/clients/{client_id}`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0016-11
- endpoint: `PATCH /api/v3/clients/{client_id}`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0016-12
- endpoint: `PATCH /api/v3/clients/{client_id}`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0055-13
- endpoint: `GET /api/v3/inventories/`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0055-14
- endpoint: `GET /api/v3/inventories/`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0055-15
- endpoint: `GET /api/v3/inventories/`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0061-16
- endpoint: `GET /api/v3/inventories/{inventory_id}`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0061-17
- endpoint: `GET /api/v3/inventories/{inventory_id}`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0061-18
- endpoint: `GET /api/v3/inventories/{inventory_id}`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0062-19
- endpoint: `PATCH /api/v3/inventories/{inventory_id}`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0062-20
- endpoint: `PATCH /api/v3/inventories/{inventory_id}`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0062-21
- endpoint: `PATCH /api/v3/inventories/{inventory_id}`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0078-22
- endpoint: `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/export`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0078-23
- endpoint: `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/export`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0078-24
- endpoint: `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/export`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0087-25
- endpoint: `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/export`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0087-26
- endpoint: `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/export`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0087-27
- endpoint: `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/export`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0094-28
- endpoint: `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/export`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0094-29
- endpoint: `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/export`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0094-30
- endpoint: `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/export`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0178-31
- endpoint: `GET /api/v3/inventories/{inventory_id}/export`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0178-32
- endpoint: `GET /api/v3/inventories/{inventory_id}/export`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0178-33
- endpoint: `GET /api/v3/inventories/{inventory_id}/export`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0179-34
- endpoint: `GET /api/v3/inventories/{inventory_id}/export/package`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0179-35
- endpoint: `GET /api/v3/inventories/{inventory_id}/export/package`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0179-36
- endpoint: `GET /api/v3/inventories/{inventory_id}/export/package`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0180-37
- endpoint: `GET /api/v3/inventories/{inventory_id}/export/summary`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0180-38
- endpoint: `GET /api/v3/inventories/{inventory_id}/export/summary`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0180-39
- endpoint: `GET /api/v3/inventories/{inventory_id}/export/summary`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0204-40
- endpoint: `GET /api/v3/inventories/{inventory_id}/metrics`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0204-41
- endpoint: `GET /api/v3/inventories/{inventory_id}/metrics`
- category_owasp: API1 BOLA
- objective: Deny company_admin of other client (other_tenant)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: client_B accessing client_A resource
- request_conceptual: other_tenant against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0204-42
- endpoint: `GET /api/v3/inventories/{inventory_id}/metrics`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0208-43
- endpoint: `POST /auth/login`
- category_owasp: API1 Broken Object Level Authorization / API2
- objective: Reject unauthenticated access (no_auth)
- preconditions: disposable local DB; synthetic clients A/B
- role: none
- tenant: n/a
- request_conceptual: no_auth against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0208-44
- endpoint: `POST /auth/login`
- category_owasp: API2 Broken Authentication
- objective: Reject invalid/expired JWT (invalid_token)
- preconditions: disposable local DB; synthetic clients A/B
- role: company_admin
- tenant: n/a
- request_conceptual: invalid_token against path with UUID from other tenant when applicable
- expected_safe: 401/403/404 fail-closed (no data leak)
- vuln_signal: 200 with foreign tenant data
- impact: cross-tenant disclosure/modification
- operational_risk: LOW for GET; MEDIUM for PATCH/POST
- environment: LOCAL_SAFE
- cleanup: none for GET; delete created rows for POST

### DAST-EP-0046-UPLOAD
- endpoint: `POST /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0068-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0071-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/authoritative-exclusion`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0074-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{source_asset_id}/manual-result`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0103-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/invalidate-result`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0107-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/reprocess`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0108-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/retry-persistence`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0109-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/send-to-external`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0176-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/dinamic-scanner-txt-imports/confirm`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0177-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/dinamic-scanner-txt-imports/preview`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0194-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/local-csv-imports/confirm`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0195-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/local-csv-imports/preview`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0197-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/local-inventory-packages/confirm`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts

### DAST-EP-0198-UPLOAD
- endpoint: `POST /api/v3/inventories/{inventory_id}/local-inventory-packages/preview`
- category_owasp: API8 Security Misconfiguration / unrestricted file upload
- objective: Reject path traversal / oversize / unexpected MIME
- preconditions: auth JWT; inventory in-scope
- request_conceptual: multipart with oversized file, `../` filename, polyglot content
- expected_safe: 413/422/400; no write outside storage root
- vuln_signal: stored outside tenant prefix or 500 with stack
- environment: LOCAL_ISOLATED_ONLY
- cleanup: delete uploaded artifacts
