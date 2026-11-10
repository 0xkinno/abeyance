"""Fault switch for the break campaign: ABEYANCE_FAULT=store|policy|drift raises inside that module.

Used to prove the fail-safe wrapper: in a cron run the step is held, in a live chat Hermes
behaves as if the plugin were not installed. Off unless the variable is set.
"""
from __future__ import annotations

import os


class InjectedFault(RuntimeError):
    pass


def check(name: str) -> None:
    if os.environ.get("ABEYANCE_FAULT", "").strip().lower() == name:
        raise InjectedFault(f"ABEYANCE_FAULT={name}")
