from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from asgiref.sync import async_to_sync
from django.http import HttpRequest
from django_service_specs import SpecRegistry
from django_spec_agents import ThreadRunStatus
from django_spec_agents.headless.types.firing_state import FiringState
from django_spec_agents.routines import RoutineSweep
from django_spec_agents.routines.run_agent_spec import run_agent_spec
from django_spec_tasks import TaskBinding, enqueue, state_of
from django_spec_tasks.backends.django_tasks_backend import DjangoTasksBackend

from agent.child_sessions import run_store, runner
from board.models import Routine

# Each firing's deadline. The lease outlasts it, or a slow firing loses its terminal write.
ROUTINE_TIMEOUT = 300.0

registry = SpecRegistry()
registry.register("run_routine", run_agent_spec(Routine, runner, timeout=ROUTINE_TIMEOUT))

routines = TaskBinding(
    name="routines",
    registry=registry,
    backend=DjangoTasksBackend(),
    lease=timedelta(seconds=ROUTINE_TIMEOUT * 2),
)

_LAPSED = {"ABANDONED", "AUTHORIZATION_LAPSED", "SPEC_UNAVAILABLE"}


class SpecTasksQueue:
    """The routine sweep's queue: a firing is a django-spec-tasks run on Django Tasks."""

    def enqueue(self, spec_name: str, params: Mapping[str, Any], *, actor: Any) -> str:
        return enqueue(routines, spec_name, dict(params), actor=actor)

    def state(self, run_id: str) -> FiringState | None:
        state = state_of(routines, run_id)
        if state is None:
            return None
        if state in {"PENDING", "RUNNING"}:
            return FiringState.PENDING
        return FiringState.LAPSED if state in _LAPSED else FiringState.FINISHED


routine_sweep = RoutineSweep(queue=SpecTasksQueue(), spec_name="run_routine")


def thread_waits(thread_id: str, principal: Any) -> bool:
    """The run store is async and scoped by a request's owner, so one is built for the principal."""
    request = HttpRequest()
    request.user = principal
    state = async_to_sync(run_store.get)(thread_id, request=request)
    return state is not None and state.status == ThreadRunStatus.WAITING
