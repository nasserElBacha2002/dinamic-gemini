# Review Package Index — Dinamic Gemini

- **branch**: `DIN-357`
- **commit**: `7e254f35c68610931f0f2aff5bc936a52bc77b39`
- **generated_at_utc**: `2026-09-14T16:35:38Z`
- **git_status_before**:

```
?? audit/september-endpoint-inventory/

```

## Recommended reading order

1. Phase 1 executive summary → tooling results → findings → roadmap
2. Worker SQL fix evidence (informational; not approved remediation)
- **total_files_in_index**: 111
- **expected**: 36
- **expected_found**: 36
- **expected_missing**: 0
- **included_in_parts**: 90
- **excluded**: 21
- **parts**: 1

3. Phase 2 endpoint executive summary → inventory → authz matrix → DAST handoff
4. OpenAPI discovered + endpoint JSON
5. Supporting tool-logs / `audit/raw` outputs as needed

## File inventory

| ID | Path | Ext | Size | SHA-256 | Phase | Category | Included | Part(s) | Duplicate | Redacted | Notes |
|----|------|-----|------|---------|-------|----------|----------|---------|-----------|----------|-------|
| PKG-0001 | `audit/september-code-audit/00-executive-summary.md` | .md | 4380 | `c41867614860a5170d371545e4e1d1ee295a95b5c15f494982b2f15e6ebc5df8` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0002 | `audit/september-code-audit/01-repository-baseline.md` | .md | 2835 | `7032bfe1cdfbb1fa4aa710a590ff3c60db22696a67e5835e35833a6e11656186` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0003 | `audit/september-code-audit/02-tooling-inventory.md` | .md | 3818 | `2da4b5ed4b49f2729f6466104546b6636c69303309e620747f8015f975ddfbfb` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0004 | `audit/september-code-audit/03-tool-execution-results.md` | .md | 3604 | `dd4bb97d14d47016b00593aa0cbe94cfaac7df34ab4c7b1e42b88ba9075d8341` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0005 | `audit/september-code-audit/04-functional-inventory.md` | .md | 3171 | `cd1c3dd629da19164fbe49cbf2ec129ffa7609d282b6dbc00c52601ea21ef9ba` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0006 | `audit/september-code-audit/05-architecture-review.md` | .md | 2464 | `4011fba4dec2463fdf6e77752873e63adc16598e002309e0b3bfdede28bbb8b5` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0007 | `audit/september-code-audit/06-security-review.md` | .md | 3783 | `0555c9144f566fa09e95e04df054a0b5afe262bf8e452a1c42ed888de164c3fa` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0008 | `audit/september-code-audit/07-quality-and-correctness-review.md` | .md | 1723 | `e29cba31412b1a4d0c3617d4578a06b3e8bb027811a027916de394a09524565b` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0009 | `audit/september-code-audit/08-test-gap-analysis.md` | .md | 1934 | `3e41caa4dbf952d339afa7b4dbd739f6d698fe28d9443b236e0500985a545ae7` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0010 | `audit/september-code-audit/09-cross-layer-consistency.md` | .md | 2005 | `60ada47ea4bb3bc91bcf9b54d83d465fdae111f92988b562b1547417110b71c5` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0011 | `audit/september-code-audit/10-findings-register.md` | .md | 6064 | `6e86a28996ae271b9b52818f56e75f72c008d85f50b0f6810b54b396062607dd` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0012 | `audit/september-code-audit/11-prioritized-remediation-roadmap.md` | .md | 1999 | `a1032f7e3dfa541de199b0b547befe22cff4339da20bbf567dfc47917a7f49eb` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0013 | `audit/september-code-audit/12-phase-2-handoff.md` | .md | 2554 | `6dbd4f4a959de57ec48f78b91d4e5fa497b4b945a04bca84d6e278b029d46a23` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0014 | `audit/september-code-audit/audit-manifest.json` | .json | 4872 | `9c143ac3cfc11a3e12d9a16748f0c3beba5799fcc3da4293670d2013dd898d7f` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0015 | `audit/audit-summary.md` | .md | 4842 | `753f05a37c41e40217e628d9b73c905a37e3815742ddd6cf6648be804ca5dad1` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0016 | `audit/audit-status.json` | .json | 13090 | `2cb6afd51d7c55d46e992f69abe1001b526cee325dfc4fccbb9849471b893c24` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0017 | `audit/september-endpoint-inventory/00-endpoint-executive-summary.md` | .md | 2336 | `06eafabfc123938a94f91dfd5aed050db22b98b89885f593bd4a8f1c495cc246` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0018 | `audit/september-endpoint-inventory/01-endpoint-inventory.md` | .md | 47581 | `7bce671431110f68afd2e243c7fd338f7059cd1b28489cad5a0d44ada6711a56` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0019 | `audit/september-endpoint-inventory/02-endpoint-inventory.csv` | .csv | 80513 | `c6e6003a5811621993abb221f9049d7ea68c71e8e5241eea73d9a92c9cc8cd82` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0020 | `audit/september-endpoint-inventory/03-authorization-matrix.md` | .md | 42055 | `a12eddfd7f9e0e6ff9a93ff07426f983d003c95693485382774e57c2903d6f12` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0021 | `audit/september-endpoint-inventory/04-resource-relationship-matrix.md` | .md | 4879 | `51b35ece23ab6beae2f2ed93cfb2a02ad25047eb68cba0b69d4f22a4bd9e2b0a` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0022 | `audit/september-endpoint-inventory/05-consumer-backend-crosscheck.md` | .md | 8502 | `30bd35f6653029812302c00a33d5bef4fe96feab83a615edbcad046be33733ca` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0023 | `audit/september-endpoint-inventory/06-dast-priority.md` | .md | 1620 | `e8a6f019cf4bc75bbda71ce473bb7e9e4006ea31228e8460f535c52ef4ef5a3e` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0024 | `audit/september-endpoint-inventory/07-dast-test-cases.md` | .md | 37255 | `d1013e85c76c7a08e5bbb45887f49577122e2b9da46a3a2b2e28fb24e009f646` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0025 | `audit/september-endpoint-inventory/08-environment-safety-matrix.md` | .md | 833 | `6e7097f8ef1b0602a4b818beec7aadaae36348041064fe56216fb8965ac27c11` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0026 | `audit/september-endpoint-inventory/09-openapi-crosscheck.md` | .md | 1070 | `5d9af60f52227a9cf266901ac2d1281195ee28e65c9a829f90466709251cc745` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0027 | `audit/september-endpoint-inventory/10-unmounted-and-legacy-routes.md` | .md | 1730 | `36e32a667863163b9377c6662aff658107fd7e4310b656fb92b5931f9941ff66` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0028 | `audit/september-endpoint-inventory/11-phase-3-security-handoff.md` | .md | 1439 | `873611714711e8f1ea12e570b231bcc2eaea9940a3d0a071d748f5de0bcf5340` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0029 | `audit/september-endpoint-inventory/openapi-discovered.yaml` | .yaml | 723340 | `92dfb34eeb0653985d78b46b59781292737dc94392b5371a4f0cb4104dfc68af` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | YES |  |
| PKG-0030 | `audit/september-endpoint-inventory/endpoint-inventory.json` | .json | 325675 | `dc280381cd14cdde4e79787f656f16034fe288797b692a543d34bf8b5820db92` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0031 | `audit/september-endpoint-inventory/endpoint-audit-manifest.json` | .json | 4253 | `3ca71c739444e19295b17f47a0ce91826766bb96e21fdd82838e860dc5cb5243` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0032 | `audit/worker-sql-repository-fix-audit.md` | .md | 4806 | `deff8aa6a017f37326119518ade1b1677df374db1e74256f1cd6fe7327e7d1bf` | WORKER_SQL_EVIDENCE | WORKER_SQL_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0033 | `audit/worker-sql-repository-fix-diff.txt` | .txt | 36306 | `7d277717fa58681e2fa6faa00927c18e3415bb6e069619030f22e39a7bedebbf` | WORKER_SQL_EVIDENCE | WORKER_SQL_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0034 | `audit/worker-sql-repository-fix-diffstat.txt` | .txt | 637 | `39a6fed7d91cca20bd6ce127c2c6b51e48c4dd2ddd5a4acf6c0a2477be26642c` | WORKER_SQL_EVIDENCE | WORKER_SQL_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0035 | `audit/worker-sql-repository-fix-status.txt` | .txt | 612 | `d2c8925a0eb6c0a19ecec2d3aa90c9188187a2aed2592cde356fd98989ec40f1` | WORKER_SQL_EVIDENCE | WORKER_SQL_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0036 | `audit/worker-sql-repository-fix-validation.md` | .md | 4089 | `029252c01f375dac5f8898816cc78e7376ec78e3d7c1311ee0b10f3d1595cbb7` | WORKER_SQL_EVIDENCE | WORKER_SQL_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0037 | `audit/september-code-audit/_audit-finished-at.txt` | .txt | 21 | `8a39e70091de1525f3e835d0c66396710136f0b85de7aef90497448fe0903318` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0038 | `audit/september-code-audit/_audit-started-at.txt` | .txt | 21 | `9c9e0230d47009e5e2f0463d5214cf629035692ab899f456f9004ab74925ed9f` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0039 | `audit/september-code-audit/_audit-tools-finished-at.txt` | .txt | 21 | `18c06d1e6c0ba52aa92e606aaefeefa2ed974fc366fb122e751859c6ff408ef7` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0040 | `audit/september-code-audit/_baseline-branch.txt` | .txt | 8 | `0e785b742c8a025269380ddaef68d37ce386407c687635b2d3310e0c8fd2d085` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0041 | `audit/september-code-audit/_baseline-commit.txt` | .txt | 41 | `cb87f03301731e4f87e36ceb30cfd5faf1aa04df78135497b5493e6e2b772c32` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0042 | `audit/september-code-audit/_baseline-git-status.txt` | .txt | 562 | `413c7a0981a7d5342ce80a24f0edec4625962edc7f957d2102e397f384474e16` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0043 | `audit/september-code-audit/_baseline-runtimes.txt` | .txt | 273 | `29ca9004d1fe3033e2beed4cd824937bddccb8acb5958ebcdf13648842870a3d` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0044 | `audit/september-code-audit/_final-git-status.txt` | .txt | 31 | `f46aba9f954953ac3d619ab817e4ea6aa4a91dc8f664005a1016ae9e4431b7f0` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0045 | `audit/september-code-audit/tool-logs/audit-status-copy.json` | .json | 13090 | `2cb6afd51d7c55d46e992f69abe1001b526cee325dfc4fccbb9849471b893c24` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt | audit/audit-status.json | NO | duplicate of `audit/audit-status.json` |
| PKG-0046 | `audit/september-code-audit/tool-logs/audit-summary-copy.md` | .md | 4842 | `753f05a37c41e40217e628d9b73c905a37e3815742ddd6cf6648be804ca5dad1` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt | audit/audit-summary.md | NO | duplicate of `audit/audit-summary.md` |
| PKG-0047 | `audit/september-code-audit/tool-logs/frontend-npm-audit-high.txt` | .txt | 651 | `b8e2b3b750fec15ec0a6632ff48a1636c7c4125560b9ac1424dc8295f62f8fe5` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0048 | `audit/september-code-audit/tool-logs/gitleaks-host-report.json` | .json | 3 | `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0049 | `audit/september-code-audit/tool-logs/gitleaks-host.log` | .log | 379 | `6899b072363d9750e47672eff3b69100d4e024546eb408cbb6ebfd401edf769b` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0050 | `audit/september-code-audit/tool-logs/mobile-npm-audit-high.txt` | .txt | 16998 | `7ef07010154f530e8e88b0b0ae756f23cd0aacdd2db8074cd4a283b82f788a53` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0051 | `audit/september-code-audit/tool-logs/run_full_audit.log` | .log | 11550 | `dad97fd323a264d36945e4d24839b63897fd7764e2bccfce0a7a4b40df92e13d` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0052 | `audit/september-code-audit/tool-logs/run_security_audit_allperms.log` | .log | 4119 | `0602f60dcc1a4b8fa6b5715478d3d4e3780309cb70db757056f45e98c264ed97` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0053 | `audit/september-code-audit/tool-logs/run_security_audit_docker.log` | .log | 4119 | `85d87139256f4cee99d01c066631c2688c944e46e61516bd6eb573331c83725e` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0054 | `audit/september-code-audit/tool-logs/run_security_audit_retry.log` | .log | 4119 | `4bf3f1502a186dee774791dd52cc5c45ac7d544990c11ef803549187f061f282` | PHASE_1_CODE_AUDIT | PHASE_1_CODE_AUDIT | YES | review-package-part-01.txt |  | NO |  |
| PKG-0055 | `audit/september-endpoint-inventory/_baseline-branch.txt` | .txt | 8 | `0e785b742c8a025269380ddaef68d37ce386407c687635b2d3310e0c8fd2d085` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0056 | `audit/september-endpoint-inventory/_baseline-commit.txt` | .txt | 41 | `1e50b409b7085986b81411a9c32269a65f1ffbebd7252ac3432f45061bc9bbe6` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0057 | `audit/september-endpoint-inventory/_baseline-git-status.txt` | .txt | 39 | `06631019b26b8dde7fb1b6ea65933ffbe355edca504ffb3365663a56776e7b54` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0058 | `audit/september-endpoint-inventory/_baseline-started-at.txt` | .txt | 21 | `9e94b8f3c73dace90968f1f6d4216ac17c66d6a39bc7f64654407f09211174cd` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0059 | `audit/september-endpoint-inventory/_fastapi_routes_raw.json` | .json | 187701 | `8e77b670ec95bcd08e3f616da93c3c527451c9d5567f672dd237c11a245f03e2` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0060 | `audit/september-endpoint-inventory/_final-git-status.txt` | .txt | 39 | `06631019b26b8dde7fb1b6ea65933ffbe355edca504ffb3365663a56776e7b54` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0061 | `audit/september-endpoint-inventory/_stats.json` | .json | 1198 | `5b75a150d67128a96515cc16e74dc37d36bd2d6a1fb231946d4d16f59edd253a` | PHASE_2_ENDPOINT_INVENTORY | PHASE_2_ENDPOINT_INVENTORY | YES | review-package-part-01.txt |  | NO |  |
| PKG-0062 | `audit/raw/LATEST_RUN.txt` | .txt | 17 | `01728bffdd526b5cc194fafb86d2a722d96e0c925e13157e32acc93a4ed91ac3` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0063 | `audit/raw/backend-bandit.json` | .json | 702529 | `b1ee97cba9f785d8565814e0bf5bac5a0b8eacf561338ee1a5746b390298d15e` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | YES |  |
| PKG-0064 | `audit/raw/backend-code-smells.txt` | .txt | 749906 | `d91fb07612160403bfa5d9a91f887a741b74ae16d1e995c9fd0e9161d85eea1f` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0065 | `audit/raw/backend-complexity.txt` | .txt | 773017 | `ba8c0873714385d710059a3d936398ed181663366c9e7d141eb673da87f8fff5` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0066 | `audit/raw/backend-gitleaks.json` | .json | 3 | `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0067 | `audit/raw/backend-import-boundaries.txt` | .txt | 3658 | `4db6637a454521f0a33884e468b37b464d8aa2255d009ff31e4be68432548062` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0068 | `audit/raw/backend-mypy.txt` | .txt | 46 | `09d5e606d033504e7458692e928892aa9a1c9ab039f6da3bc163712535883e27` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0069 | `audit/raw/backend-pip-audit.json` | .json | 187 | `67198a7e5de477ae0bd5edcc154ec8e624e9378f4b610feadf643cbcc108d572` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0070 | `audit/raw/backend-pytest.txt` | .txt | 232594 | `21065dcdc55b6ebd0e0d783cf8baf8f620fcc969e04a323c45261fc0de030ee5` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0071 | `audit/raw/backend-ruff.txt` | .txt | 19 | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0072 | `audit/raw/backend-solid-grasp-audit.md` | .md | 3714 | `e040701b6a3e317c8428585990896fdb551c2cfaef4fd71105e351f060f819b8` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0073 | `audit/raw/frontend-code-smells.txt` | .txt | 7527 | `cfbbdd8f5367a38c95237c7bac35a022303f12ffdb5ee211b88d6bb76ebf136c` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0074 | `audit/raw/frontend-complexity.txt` | .txt | 3161 | `32b236bbfeae7c6f307fb89b1ea4d1ef161003ad8b856ff906e67fec6649b404` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0075 | `audit/raw/frontend-dead-code.txt` | .txt | 75323 | `19f7fe23359f577e9c00d6dd21e4986896fa4e72e1e0cf3fcee5136f64866ca0` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0076 | `audit/raw/frontend-duplication.txt` | .txt | 7438 | `3bfd56993fb0cdfe635c26a28d3b9570fec72b06c13ca6c6316486adb4d512fa` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0077 | `audit/raw/frontend-error-handling-audit.md` | .md | 12624 | `cceb0d97945876ffc0c693519b20210c68938103f3c44a31ab58f7a964c17e5a` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0078 | `audit/raw/frontend-eslint.txt` | .txt | 7351 | `cd6e8d0748abcbc07a0bf1e44d1a27b72660753e641c95e03af49a1618185241` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0079 | `audit/raw/frontend-import-boundaries.txt` | .txt | 1752 | `a37931980571d81fa1bb4262d34f29874efc412e7d53ced793319f987f5dccc8` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0080 | `audit/raw/frontend-npm-audit.json` | .json | 2340 | `e59c24eb550c8a66cab0870b37eb71ae2a60a394865050fd79893c6d14e2a846` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0081 | `audit/raw/frontend-reusable-components-audit.md` | .md | 1264 | `bfe65d405560c0271c357f5418010d3dbcc713c3f6904e65eca5b69003852546` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0082 | `audit/raw/frontend-solid-react-audit.md` | .md | 415 | `027470edfdf0f5cef7c4d3b29b96435ebc62c43778c4849242b64e4161eadd70` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0083 | `audit/raw/frontend-typecheck.txt` | .txt | 177 | `66a33f4bff3a3134316fa063e27a2242ef5a382eea75329dfd13bdc67f51d697` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0084 | `audit/raw/frontend-useeffects-audit.md` | .md | 3568 | `1e1ae58a7010fafe81187b4b3c8395e83120d64a41d380c250f83794e048c160` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0085 | `audit/raw/frontend-vitest.txt` | .txt | 112092 | `154e01ee3663c261a00571b85160f4ea63384bd4ca033638ee8fb28053eec287` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0086 | `audit/raw/mobile-jest.txt` | .txt | 6189 | `9f1a643c2134abc4e68c4d658d54b1ae3b4256019254e599a99058384fafbd25` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0087 | `audit/raw/mobile-lint.txt` | .txt | 178 | `bce453419a052a333e555639610693aac3f2df9f4c7fee448278fd99d89958a9` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0088 | `audit/raw/mobile-npm-audit.json` | .json | 48699 | `9aea20f3fb5cfc0bb6fcadeed51ef1208691e9381c4decebeb572fa3301bf808` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0089 | `audit/raw/mobile-typecheck.txt` | .txt | 155 | `67c26f31b6096c6ba8dafce8d3d61b20c3f382c013785ba0df9ac461a78d693b` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0090 | `audit/raw/python-env.json` | .json | 850 | `5266779ab0ce5d251a4439a40f0f38659ec4303bbbb5353f252329bec97f999b` | SUPPORTING_EVIDENCE | SUPPORTING_EVIDENCE | YES | review-package-part-01.txt |  | NO |  |
| PKG-0091 | `audit/Archivo.zip` | .zip | 753307 | `a80bf68943239e7b5efd81f389f728cd963d45bec68b83d4d5afc725ebc11564` | — | EXCLUDED | NO |  |  | NO | binary ZIP excluded per package rules |
| PKG-0092 | `audit/codex-pruebas-b-fix-validation.md` | .md | 4158 | `de8b99541086e6c111487762a6da9234a5ca544f36dd77ba5ee7316a1fab0728` | — | EXCLUDED | NO |  |  | NO | not part of september code-audit / endpoint-inventory / worker-sql package (separate investigation/design) |
| PKG-0093 | `audit/codex-pruebas-b-root-cause.md` | .md | 8341 | `27f2a447ea88c6421cf2e4614ab5dca35801d86fe98439c09a388df6ade4b123` | — | EXCLUDED | NO |  |  | NO | not part of september code-audit / endpoint-inventory / worker-sql package (separate investigation/design) |
| PKG-0094 | `audit/implementation-corrections-validation.md` | .md | 1939 | `9f058f1ad939d62f5b5024d7839ed153e115c6429d171bc1b5987f5efec90ebd` | — | EXCLUDED | NO |  |  | NO | not part of september code-audit / endpoint-inventory / worker-sql package (separate investigation/design) |
| PKG-0095 | `audit/mobile-export-pruebas-b-real-first-divergence.md` | .md | 17195 | `0b3808276347d33c8ae7c35ba399bc9de2c055d2e162b430c53086ff64dd72b0` | — | EXCLUDED | NO |  |  | NO | not part of september code-audit / endpoint-inventory / worker-sql package (separate investigation/design) |
| PKG-0096 | `audit/online-aisle-create-materialization-root-cause.md` | .md | 4025 | `7cae08edacf306384106c336efe6b63457cae1d95c11b8ffbb13ac63aefd7496` | — | EXCLUDED | NO |  |  | NO | not part of september code-audit / endpoint-inventory / worker-sql package (separate investigation/design) |
| PKG-0097 | `audit/raw/backend-bandit.json.exitcode` | .exitcode | 2 | `4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0098 | `audit/raw/backend-gitleaks.json.exitcode` | .exitcode | 4 | `703d2c10fa601276a4dd96193faed68902a642a44eb5b01b40d6fc8499e12822` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0099 | `audit/raw/backend-mypy.txt.exitcode` | .exitcode | 2 | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0100 | `audit/raw/backend-pip-audit.json.exitcode` | .exitcode | 2 | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0101 | `audit/raw/backend-pytest.txt.exitcode` | .exitcode | 2 | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0102 | `audit/raw/backend-ruff.txt.exitcode` | .exitcode | 2 | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0103 | `audit/raw/frontend-eslint.txt.exitcode` | .exitcode | 2 | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0104 | `audit/raw/frontend-npm-audit.json.exitcode` | .exitcode | 2 | `4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0105 | `audit/raw/frontend-typecheck.txt.exitcode` | .exitcode | 2 | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0106 | `audit/raw/frontend-vitest.txt.exitcode` | .exitcode | 2 | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0107 | `audit/raw/mobile-jest.txt.exitcode` | .exitcode | 2 | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0108 | `audit/raw/mobile-lint.txt.exitcode` | .exitcode | 2 | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0109 | `audit/raw/mobile-npm-audit.json.exitcode` | .exitcode | 2 | `4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0110 | `audit/raw/mobile-typecheck.txt.exitcode` | .exitcode | 2 | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` | — | EXCLUDED | NO |  |  | NO | exitcode companion file; trivial noise for review chat |
| PKG-0111 | `audit/supplier-aware-local-csv-import-design.md` | .md | 2682 | `173971ea46116ad6da62a128f5735de3b847778f90d7bacabc31cc4284db082a` | — | EXCLUDED | NO |  |  | NO | not part of september code-audit / endpoint-inventory / worker-sql package (separate investigation/design) |

## Expected but missing

None. All expected Phase 1 / Phase 2 / Worker SQL / alternate summary files were found.

## Additional files included (beyond expected list)

- `audit/september-code-audit/_audit-finished-at.txt` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/_audit-started-at.txt` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/_audit-tools-finished-at.txt` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/_baseline-branch.txt` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/_baseline-commit.txt` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/_baseline-git-status.txt` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/_baseline-runtimes.txt` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/_final-git-status.txt` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/tool-logs/audit-status-copy.json` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/tool-logs/audit-summary-copy.md` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/tool-logs/frontend-npm-audit-high.txt` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/tool-logs/gitleaks-host-report.json` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/tool-logs/gitleaks-host.log` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/tool-logs/mobile-npm-audit-high.txt` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/tool-logs/run_full_audit.log` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/tool-logs/run_security_audit_allperms.log` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/tool-logs/run_security_audit_docker.log` (PHASE_1_CODE_AUDIT)
- `audit/september-code-audit/tool-logs/run_security_audit_retry.log` (PHASE_1_CODE_AUDIT)
- `audit/september-endpoint-inventory/_baseline-branch.txt` (PHASE_2_ENDPOINT_INVENTORY)
- `audit/september-endpoint-inventory/_baseline-commit.txt` (PHASE_2_ENDPOINT_INVENTORY)
- `audit/september-endpoint-inventory/_baseline-git-status.txt` (PHASE_2_ENDPOINT_INVENTORY)
- `audit/september-endpoint-inventory/_baseline-started-at.txt` (PHASE_2_ENDPOINT_INVENTORY)
- `audit/september-endpoint-inventory/_fastapi_routes_raw.json` (PHASE_2_ENDPOINT_INVENTORY)
- `audit/september-endpoint-inventory/_final-git-status.txt` (PHASE_2_ENDPOINT_INVENTORY)
- `audit/september-endpoint-inventory/_stats.json` (PHASE_2_ENDPOINT_INVENTORY)
- `audit/raw/LATEST_RUN.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/backend-bandit.json` (SUPPORTING_EVIDENCE)
- `audit/raw/backend-code-smells.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/backend-complexity.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/backend-gitleaks.json` (SUPPORTING_EVIDENCE)
- `audit/raw/backend-import-boundaries.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/backend-mypy.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/backend-pip-audit.json` (SUPPORTING_EVIDENCE)
- `audit/raw/backend-pytest.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/backend-ruff.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/backend-solid-grasp-audit.md` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-code-smells.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-complexity.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-dead-code.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-duplication.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-error-handling-audit.md` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-eslint.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-import-boundaries.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-npm-audit.json` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-reusable-components-audit.md` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-solid-react-audit.md` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-typecheck.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-useeffects-audit.md` (SUPPORTING_EVIDENCE)
- `audit/raw/frontend-vitest.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/mobile-jest.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/mobile-lint.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/mobile-npm-audit.json` (SUPPORTING_EVIDENCE)
- `audit/raw/mobile-typecheck.txt` (SUPPORTING_EVIDENCE)
- `audit/raw/python-env.json` (SUPPORTING_EVIDENCE)

## Excluded files

- `audit/Archivo.zip` — binary ZIP excluded per package rules — exists=True
- `audit/codex-pruebas-b-fix-validation.md` — not part of september code-audit / endpoint-inventory / worker-sql package (separate investigation/design) — exists=True
- `audit/codex-pruebas-b-root-cause.md` — not part of september code-audit / endpoint-inventory / worker-sql package (separate investigation/design) — exists=True
- `audit/mobile-export-pruebas-b-real-first-divergence.md` — not part of september code-audit / endpoint-inventory / worker-sql package (separate investigation/design) — exists=True
- `audit/online-aisle-create-materialization-root-cause.md` — not part of september code-audit / endpoint-inventory / worker-sql package (separate investigation/design) — exists=True
- `audit/supplier-aware-local-csv-import-design.md` — not part of september code-audit / endpoint-inventory / worker-sql package (separate investigation/design) — exists=True
- `audit/implementation-corrections-validation.md` — not part of september code-audit / endpoint-inventory / worker-sql package (separate investigation/design) — exists=True
- `audit/raw/backend-pytest.txt.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/frontend-eslint.txt.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/frontend-typecheck.txt.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/mobile-jest.txt.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/backend-ruff.txt.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/backend-bandit.json.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/backend-pip-audit.json.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/frontend-vitest.txt.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/mobile-lint.txt.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/mobile-npm-audit.json.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/mobile-typecheck.txt.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/backend-gitleaks.json.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/backend-mypy.txt.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
- `audit/raw/frontend-npm-audit.json.exitcode` — exitcode companion file; trivial noise for review chat — exists=True
