"""Operator dashboard (ADR-0010, REQ-05): FastAPI websocket + one static page in web/.

Shows: map (truth if known, estimate, error ellipse), HPL vs alert limit, timing uncertainty,
per-source trust/health, status (nominal / degraded / unsafe), and event flags.
Fed by any source (sim, replay, live), like the estimator.
"""
