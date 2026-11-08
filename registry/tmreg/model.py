"""Field lists, vocabularies, and labels. Constants only."""

RISK_FIELDS = (
    "id", "title", "elements", "category", "method", "origin", "origin_ref", "description",
    "attack_scenario", "attack_path", "impact", "impact_rating", "likelihood",
    "likelihood_rationale", "score", "score_method", "assumptions", "implemented_controls",
    "recommended_controls", "control_refs", "exception_ref", "treatment", "decision_requested",
    "evidence", "ai_confidence", "owner", "due", "status", "status_reason", "test", "ticket",
    "notes", "review_state", "last_approved", "drafted_by", "reviewed_by", "reviewed_at",
    "review_note", "possible_duplicate_of", "merged_into", "dfd_approval_id", "detail_complete",
    "created_at", "updated_at",
)

EDITABLE_FIELDS = tuple(
    f for f in RISK_FIELDS[RISK_FIELDS.index("title"):RISK_FIELDS.index("notes") + 1]
    if f != "status_reason"
)

SYSTEM_FIELDS = tuple(f for f in RISK_FIELDS if f not in EDITABLE_FIELDS)

SNAPSHOT_FIELDS = EDITABLE_FIELDS + (
    "reviewed_by", "reviewed_at", "review_note", "dfd_approval_id", "updated_at",
)

JSON_FIELDS = ("elements", "control_refs", "last_approved")

# Per-table JSON-encoded columns and the column that holds each table's row key.
JSON_COLUMNS = {"risks": JSON_FIELDS, "dfd_approvals": ("ids",), "runs": ()}
KEY_COLUMNS = {"risks": "id", "dfd_approvals": "id", "runs": "run_id"}

AI_REQUIRED = (
    "title", "elements", "category", "method", "origin", "origin_ref", "description",
    "attack_scenario", "impact", "likelihood", "likelihood_rationale", "implemented_controls",
    "recommended_controls", "assumptions", "evidence", "ai_confidence",
)

HUMAN_REQUIRED = ("title", "elements", "category", "origin", "description")

MIN_LENGTHS = {"description": 80, "attack_scenario": 80}
NOTE_MIN = 20

STRIDE = ("S", "T", "R", "I", "D", "E")
LINDDUN = (
    "Linking", "Identifying", "Non-repudiation", "Detecting", "Data disclosure",
    "Unawareness and unintervenability", "Non-compliance",
)

# `superseded-by-<ID>` is also a valid status; it is matched by SUPERSEDED_RE.
# `retired` is listed here but only the retire command may set it.
STATUSES = ("open", "planned", "in-progress", "mitigated", "accepted", "wont-fix", "retired")
TREATMENTS = ("mitigate", "eliminate", "transfer", "accept")
CONFIDENCE = ("low", "medium", "high")
REVIEW_STATES = ("pending", "approved", "rejected")
SUPERSEDED_RE = r"^superseded-by-P?T-\d{2,}$"

LABELS = {
    "id": "ID",
    "title": "Title",
    "elements": "Elements",
    "category": "Category",
    "method": "Method",
    "origin": "Origin",
    "origin_ref": "Origin reference",
    "description": "Description",
    "attack_scenario": "Attack scenario",
    "attack_path": "Attack path",
    "impact": "Impact",
    "impact_rating": "Impact rating",
    "likelihood": "Likelihood",
    "likelihood_rationale": "Likelihood rationale",
    "score": "Score",
    "score_method": "Score method",
    "assumptions": "Assumptions",
    "implemented_controls": "Implemented controls",
    "recommended_controls": "Recommended controls",
    "control_refs": "Control references",
    "exception_ref": "Exception reference",
    "treatment": "Treatment",
    "decision_requested": "Decision requested",
    "evidence": "Evidence",
    "ai_confidence": "AI confidence",
    "owner": "Owner",
    "due": "Due",
    "status": "Status",
    "status_reason": "Status reason",
    "test": "Test",
    "ticket": "Ticket",
    "notes": "Notes",
    "review_state": "Review state",
    "last_approved": "Last approved",
    "drafted_by": "Drafted by",
    "reviewed_by": "Reviewed by",
    "reviewed_at": "Reviewed at",
    "review_note": "Review note",
    "possible_duplicate_of": "Possible duplicate of",
    "merged_into": "Merged into",
    "dfd_approval_id": "DFD approval",
    "detail_complete": "Detail complete",
    "created_at": "Created at",
    "updated_at": "Updated at",
}
