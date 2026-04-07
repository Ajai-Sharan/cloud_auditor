# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Data models for the CloudSecurityAuditor-v1 OpenEnv environment."""

from openenv.core.env_server.types import Action, Observation
from pydantic import Field


class CloudAuditorAction(Action):
    """Single-step action represented as a simulated cloud CLI command."""

    command: str = Field(
        ...,
        description=(
            "Simulated CLI command (for example: 'describe_instances' or "
            "'revoke_security_group_ingress --group-id sg-web --port 22 --cidr 0.0.0.0/0')."
        ),
    )


class CloudAuditorObservation(Observation):
    """Typed step/reset observation for the cloud security simulation."""

    task_id: str = Field(..., description="Current task identifier")
    task_description: str = Field(..., description="Natural language objective")
    command_output: str = Field(
        default="", description="Console-style output returned by the simulator"
    )
    task_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Deterministic task score from the task grader",
    )
    steps_remaining: int = Field(
        default=0, ge=0, description="Remaining steps before episode termination"
    )
    status: str = Field(
        default="running",
        description="Episode status: running, completed, or failed",
    )
