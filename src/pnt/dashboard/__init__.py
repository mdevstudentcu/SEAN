"""Operator dashboard (ADR-0027, REQ-05): FastAPI + one static page in web/, frames pushed over
Server-Sent Events (`server.py` says why not a websocket).

Shows: map (truth if known, estimate, error ellipse, HPL circle, towers, reference station),
HPL vs the alert limit with the pre-flight prediction, timing uncertainty, per-source trust,
status and flags in plain words, latched alerts (`health.py`).
Fed by any source (sim, replay, live), like the estimator (`feed.py`).

    pnt dash <session> [--estimator ekf] [--speed 4]      # replay a recorded session
    pnt sim <scenario> --dash [--estimator ekf]           # a scenario, nothing recorded
"""
