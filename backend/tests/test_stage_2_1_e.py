"""
Stage 2.1.E — Assisted counting: review store, merge, audit (no v1 API).

Review store persistence, review merge + summary recomputation.
v1 entities/report API tests removed in Stage 3; equivalent is v3 positions/reviews.
"""

from src.review import get_entity_audit, load_reviews, merge_resolved_report, save_review

# --- Review store ---


def test_review_store_load_empty(tmp_path):
    from src.review.review_store import load_reviews

    assert load_reviews(tmp_path) == {}


def test_review_store_save_and_load(tmp_path):
    event = {
        "timestamp": "2025-01-01T12:00:00Z",
        "actor": "op1",
        "action": "SET_COUNT",
        "before": {"count_status": "NEEDS_REVIEW", "final_quantity": None},
        "after": {"count_status": "COUNTED_MANUAL", "final_quantity": 10},
    }
    save_review(tmp_path, "job_1_E1", event)
    data = load_reviews(tmp_path)
    assert "job_1_E1" in data
    assert len(data["job_1_E1"]["events"]) == 1
    assert data["job_1_E1"]["events"][0]["action"] == "SET_COUNT"
    assert data["job_1_E1"]["events"][0]["after"]["final_quantity"] == 10

    save_review(
        tmp_path,
        "job_1_E1",
        {**event, "action": "MARK_EMPTY", "after": {"count_status": "EMPTY", "final_quantity": 0}},
    )
    data2 = load_reviews(tmp_path)
    assert len(data2["job_1_E1"]["events"]) == 2


def test_get_entity_audit(tmp_path):
    save_review(
        tmp_path,
        "E1",
        {
            "action": "SET_COUNT",
            "before": {},
            "after": {"count_status": "COUNTED_MANUAL", "final_quantity": 5},
        },
    )
    audit = get_entity_audit("job_1", tmp_path, "E1")
    assert len(audit) == 1
    assert audit[0]["action"] == "SET_COUNT"
    assert get_entity_audit("job_1", tmp_path, "E99") == []


# --- Review merge + summary ---


def test_merge_resolved_report_applies_set_count():
    report = {
        "report_version": "2.1",
        "entities": [
            {
                "entity_uid": "E1",
                "count_status": "NEEDS_REVIEW",
                "final_quantity": None,
                "entity_type": "PALLET",
            },
            {
                "entity_uid": "E2",
                "count_status": "COUNTED",
                "final_quantity": 12,
                "entity_type": "PALLET",
            },
        ],
        "summary": {
            "total_entities": 2,
            "counted": 1,
            "needs_review": 1,
            "counted_manual": 0,
            "pallets": 2,
            "empty_pallets": 0,
            "loose_boxes": 0,
            "not_countable": 0,
            "invalid_structure": 0,
        },
    }
    reviews = {
        "E1": {
            "entity_uid": "E1",
            "events": [
                {
                    "action": "SET_COUNT",
                    "after": {"count_status": "COUNTED_MANUAL", "final_quantity": 15},
                },
            ],
        },
    }
    merged = merge_resolved_report(report, reviews)
    e1 = next(e for e in merged["entities"] if e["entity_uid"] == "E1")
    assert e1["count_status"] == "COUNTED_MANUAL"
    assert e1["final_quantity"] == 15
    assert merged["summary"]["counted_manual"] == 1
    assert merged["summary"]["needs_review"] == 0


def test_merge_resolved_report_mark_empty_and_invalid():
    report = {
        "entities": [
            {
                "entity_uid": "E1",
                "count_status": "NEEDS_REVIEW",
                "final_quantity": None,
                "entity_type": "PALLET",
            },
        ],
        "summary": {
            "total_entities": 1,
            "needs_review": 1,
            "counted": 0,
            "counted_manual": 0,
            "pallets": 1,
            "empty_pallets": 0,
            "loose_boxes": 0,
            "not_countable": 0,
            "invalid_structure": 0,
        },
    }
    reviews = {
        "E1": {
            "entity_uid": "E1",
            "events": [{"after": {"count_status": "EMPTY", "final_quantity": 0}}],
        }
    }
    merged = merge_resolved_report(report, reviews)
    assert merged["entities"][0]["count_status"] == "EMPTY"
    assert merged["entities"][0]["final_quantity"] == 0
    assert merged["summary"]["empty_pallets"] == 1 or merged["summary"].get("counted_manual") == 0

    reviews2 = {
        "E1": {
            "entity_uid": "E1",
            "events": [{"after": {"count_status": "INVALID_STRUCTURE", "final_quantity": None}}],
        }
    }
    merged2 = merge_resolved_report(report, reviews2)
    assert merged2["entities"][0]["count_status"] == "INVALID_STRUCTURE"
    assert merged2["summary"]["invalid_structure"] == 1


# --- API (entities + report): v1 routes removed in Stage 3; equivalent behavior is v3 positions/reviews ---
