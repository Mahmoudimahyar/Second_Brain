"""V1.5b/V1.5c — FastAPI middleware modules.

W2-4 adds the UI-action audit middleware (``audit_ui.UIAuditMiddleware``)
to close the gap-audit MED-5 finding: V1.5b NFR-8 specified ``ui_view`` /
``ui_select`` / ``ui_filter_change`` / ``ui_review_commit`` /
``ui_batch_commit`` / ``ui_settings_update`` audit kinds that were
declared but never wired.
"""
