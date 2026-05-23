from __future__ import annotations

import asyncio
from pathlib import Path

from asr.agents.base import BaseAgent
from asr.events.store import EventStore


class AgentRunner:
    def __init__(
        self,
        agent: BaseAgent,
        event_store: EventStore,
        poll_interval: float = 0.1,
    ):
        self._agent = agent
        self._event_store = event_store
        self._poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def agent(self) -> BaseAgent:
        return self._agent

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        processed_ids: set[str] = set()

        while self._running:
            try:
                events = self._agent.poll_inbox()
                for event in events:
                    if event.event_id not in processed_ids:
                        processed_ids.add(event.event_id)
                        results = await self._agent.process(event)
                        await self._agent.emit(results)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

            await asyncio.sleep(self._poll_interval)


class AgentOrchestrator:
    def __init__(self, event_store: EventStore):
        self._event_store = event_store
        self._runners: dict[str, AgentRunner] = {}

    def register(self, name: str, runner: AgentRunner) -> None:
        self._runners[name] = runner

    async def start_all(self) -> None:
        for runner in self._runners.values():
            await runner.start()

    async def stop_all(self) -> None:
        for runner in self._runners.values():
            await runner.stop()

    async def run_until_converged(
        self,
        controller_coro,
        max_wait: float = 300.0,
    ):
        await self.start_all()
        try:
            result = await asyncio.wait_for(controller_coro, timeout=max_wait)
            await asyncio.sleep(0.5)
            return result
        finally:
            await self.stop_all()
