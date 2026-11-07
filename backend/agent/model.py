"""Which model the demo agent runs on.

Offline by default, so `make demo` works with no account anywhere and CI can
drive the whole gallery. Set `DEMO_MODEL` to any Pydantic-AI model string to use
a real one — the rest of the wiring is identical, which is the property worth
demonstrating.
"""

from __future__ import annotations

import os
from typing import Any

from agent.scripted import build_scripted_model, build_scripted_planner


def build_demo_model() -> Any:
    """A real model when `DEMO_MODEL` is set, otherwise the scripted stand-in."""
    configured = os.environ.get("DEMO_MODEL", "").strip()
    if configured:
        # Needs the provider's own extra installed, e.g.
        # `uv add "pydantic-ai-slim[anthropic]"`, plus its API key in the
        # environment.
        return configured
    return build_scripted_model()


def build_planner_model() -> Any:
    """The planner sub-agent's model: the same choice, its own script.

    A delegated run is a separate run with a separate model, so the offline
    stand-in needs a script of its own -- the parent's script answers a person,
    and the planner is answering the parent.
    """
    configured = os.environ.get("DEMO_MODEL", "").strip()
    return configured or build_scripted_planner()


def is_offline() -> bool:
    return not os.environ.get("DEMO_MODEL", "").strip()
