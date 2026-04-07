# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""CloudSecurityAuditor-v1 Environment Client."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

from .models import CloudAuditorAction, CloudAuditorObservation


class CloudAuditorEnv(
    EnvClient[CloudAuditorAction, CloudAuditorObservation, State]
):
    """
    Client for the CloudSecurityAuditor-v1 environment.

    This client maintains a persistent WebSocket connection to the environment server,
    enabling efficient multi-step interactions with lower latency.
    Each client instance has its own dedicated environment session on the server.

    Example:
        >>> # Connect to a running server
        >>> with CloudAuditorEnv(base_url="http://localhost:8000") as client:
        ...     result = client.reset()
        ...     print(result.observation.command_output)
        ...
        ...     result = client.step(CloudAuditorAction(command="describe_instances"))
        ...     print(result.observation.task_score)

    Example with Docker:
        >>> # Automatically start container and connect
        >>> client = CloudAuditorEnv.from_docker_image("cloud_auditor-env:latest")
        >>> try:
        ...     result = client.reset()
        ...     result = client.step(CloudAuditorAction(command="describe_instances"))
        ... finally:
        ...     client.close()
    """

    def _step_payload(self, action: CloudAuditorAction) -> Dict:
        """
        Convert CloudAuditorAction to JSON payload for step message.

        Args:
            action: CloudAuditorAction instance

        Returns:
            Dictionary representation suitable for JSON encoding
        """
        return {"command": action.command}

    def _parse_result(self, payload: Dict) -> StepResult[CloudAuditorObservation]:
        """
        Parse server response into StepResult[CloudAuditorObservation].

        Args:
            payload: JSON response data from server

        Returns:
            StepResult with CloudAuditorObservation
        """
        obs_data = payload.get("observation", {})
        observation = CloudAuditorObservation(
            task_id=obs_data.get("task_id", ""),
            task_description=obs_data.get("task_description", ""),
            command_output=obs_data.get("command_output", ""),
            task_score=obs_data.get("task_score", 0.0),
            steps_remaining=obs_data.get("steps_remaining", 0),
            status=obs_data.get("status", "running"),
            done=payload.get("done", False),
            reward=payload.get("reward"),
            metadata=obs_data.get("metadata", {}),
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        """
        Parse server response into State object.

        Args:
            payload: JSON response from state request

        Returns:
            State object with episode_id and step_count
        """
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )
