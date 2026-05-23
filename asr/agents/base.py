from __future__ import annotations

from abc import ABC, abstractmethod

from asr.events.models import Event, AgentName
from asr.events.store import EventStore


class BaseAgent(ABC):
    def __init__(
        self,
        name: AgentName,
        event_store: EventStore,
    ):
        self._name = name
        self._event_store = event_store

    @property
    def name(self) -> AgentName:
        return self._name

    @abstractmethod
    async def process(self, event: Event) -> list[Event]:
        ...

    def validate_event(self, event: Event) -> bool:
        return event.to_agent == self._name

    async def emit(self, events: list[Event]) -> None:
        for evt in events:
            self._event_store.write_event(evt)

    async def poll_inbox(self) -> list[Event]:
        return self._event_store.poll_inbox(self._name)
