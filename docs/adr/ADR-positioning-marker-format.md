# ADR: Positioning label marker format

- **Status:** Accepted
- **Date:** 2026-07-31
- **Context:** Fase 2 — generate printable positioning labels (`DINAMIC_POSITION`) for physical aisle locations, readable later from handheld and drone imagery.

## Decision

Use **QR Code (ISO/IEC 18004)** as the primary machine-readable marker on positioning labels.

Payload carried in the QR is the canonical signed JSON (UTF-8), not a URL and not descriptive warehouse text.

## Options compared

| Criterion | QR | Data Matrix | ArUco | AprilTag | Combined (QR + ArUco) |
|-----------|----|-------------|-------|----------|------------------------|
| Distance / drone | Good at print size with high ECC | Good at small physical size | Excellent for pose | Excellent for pose | Best of both, denser layout |
| Perspective / blur / dirt | Strong with ECC-H | Strong | Designed for this | Designed for this | Strong |
| Rotation | Full | Full | Full | Full | Full |
| Print (mono thermal/laser) | Excellent | Excellent | Excellent | Excellent | Excellent |
| Payload density (signed JSON ~120–200 B) | Comfortable | Comfortable | Poor (ID only) | Poor (ID only) | QR carries payload |
| Python support | `qrcode` / OpenCV decode | Limited std libs | OpenCV contrib | `pupil-apriltags` / OpenCV | Two stacks |
| Android support | Native / ZXing / ML Kit | ZXing | OpenCV | AprilTag libs | Heavier APK |
| License | Public / library MIT | Public | BSD-ish OpenCV | BSD | Mixed |
| Layout quiet zone | Well understood | Well understood | Border required | Border required | Larger label |

## Rationale

1. **Payload:** Positioning labels must embed a signed, versioned `DINAMIC_POSITION` object (`label_id`, `position_id`, `key_version`, `signature`). Fiducials (ArUco/AprilTag) encode integer IDs only — they would force an online lookup or a second code. QR carries the full offline-verifiable payload.
2. **Ecosystem:** Both backend (Python) and future Android decode paths already have mature QR encode/decode libraries without proprietary SDKs.
3. **Print:** High-contrast QR with ECC level **H**, quiet zone ≥ 4 modules, and exact mm presets is proven for warehouse labels.
4. **Drone/readability:** At 100×100 mm and 100×150 mm presets with a large marker region, QR remains readable under moderate perspective and distance for inventory flights; pose estimation can be added later with a **secondary** ArUco without changing the signed payload.

## Consequences

- Marker bytes = canonical signed JSON string encoded as QR.
- `marker_version` starts at `1` (QR ECC-H, module layout per renderer template).
- Future `marker_version=2` may add a secondary ArUco for pose; payload contract stays QR-borne.
- Item (product) labels remain a separate system and must not embed position fields.

## Non-goals

- Visual detection / reconciliation (later phase).
- Changing `CODE_SCAN` or item-label payloads.
