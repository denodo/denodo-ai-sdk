"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

from enum import Enum

class Status(str, Enum):
    """Validation status levels reported at startup for agents, skills and AI Spaces."""
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"

    def __str__(self):
        return self.value

def add_status(report, name, status):
    """Append a status entry to `report` (no-op when `report` is None)."""
    if report is not None:
        report.append({"name": name, "status": Status(status)})
