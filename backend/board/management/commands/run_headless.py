"""Start one run on the board mount with no browser, and report where it stopped."""

from __future__ import annotations

import asyncio
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser
from django_ag_ui import AGUIHeadlessRunner

from agent.server import agent

DEFAULT_PROMPT = "book a design sync on Friday at 14:00"


async def run_headless(prompt: str, username: str, timeout: float) -> Any:
    user = await get_user_model().objects.aget(username=username)
    runner = AGUIHeadlessRunner(agent)
    return await runner.run_to_first_stop("board", prompt, user, timeout=timeout)


class Command(BaseCommand):
    help = "Run a prompt on the board agent headlessly; a gated call parks the thread."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT)
        parser.add_argument("--user", default="demo")
        parser.add_argument("--timeout", type=float, default=60.0)

    def handle(self, *args: Any, **options: Any) -> None:
        stop = asyncio.run(run_headless(options["prompt"], options["user"], options["timeout"]))
        self.stdout.write(f"thread={stop.thread_id} run={stop.run_id} outcome={stop.outcome.value}")
