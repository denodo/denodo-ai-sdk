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
from dataclasses import dataclass, field

class ExecutionStatus(str, Enum):
    """The closed set of statuses a VQL execution can have."""
    SUCCESS = "success"                    # 200, rows present, no executionErrors
    EMPTY = "empty"                        # 200, zero rows, no executionErrors
    EXECUTION_ERROR = "execution_error"    # 200, executionErrors[] populated
    VALIDATION_ERROR = "validation_error"  # 400-500
    CONNECTION_ERROR = "connection_error"  # connection error/timeout

@dataclass
class ExecutionOutcome:
    """The result of executing a VQL query against the Data Marketplace."""
    status: ExecutionStatus
    http_status: int = 0
    data: dict = field(default_factory=dict)   # VQL execution result; only populated for SUCCESS
    error: str = ""                            # human-readable error text
    raw: object = None                         # original response body, for debugging

    @property
    def is_success(self) -> bool:
        return self.status is ExecutionStatus.SUCCESS

    @property
    def is_empty(self) -> bool:
        return self.status is ExecutionStatus.EMPTY

    @property
    def needs_review(self) -> bool:
        """EMPTY results are sent to the query reviewer to verify the generated VQL query."""
        return self.status is ExecutionStatus.EMPTY

    @property
    def needs_fix(self) -> bool:
        """Errors are sent to the query fixer together with the error and the VQL query to fix it."""
        return self.status in (
            ExecutionStatus.EXECUTION_ERROR,
            ExecutionStatus.VALIDATION_ERROR,
            ExecutionStatus.CONNECTION_ERROR,
        )
