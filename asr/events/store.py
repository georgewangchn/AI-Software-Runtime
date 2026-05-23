from __future__ import annotations

import json
from pathlib import Path

from filelock import FileLock

from asr.events.models import Event, EventType, AgentName, event_from_dict


class EventStore:
    def __init__(self, event_dir: str | Path = ".runtime/events"):
        self._event_dir = Path(event_dir)
        self._event_dir.mkdir(parents=True, exist_ok=True)
        self._patches_dir = Path(".runtime/patches")
        self._patches_dir.mkdir(parents=True, exist_ok=True)
        self._diffs_dir = Path(".runtime/diffs")
        self._diffs_dir.mkdir(parents=True, exist_ok=True)
        self._state_dir = Path(".runtime/state")
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._tasks_dir = Path(".runtime/tasks")
        self._tasks_dir.mkdir(parents=True, exist_ok=True)

    def write_event(self, event: Event) -> str:
        event_path = self._event_dir / f"{event.event_id}.json"
        lock_path = self._event_dir / f"{event.event_id}.lock"
        lock = FileLock(str(lock_path), timeout=10, lifetime=300)

        with lock:
            tmp_path = self._event_dir / f"{event.event_id}.tmp"
            tmp_path.write_text(event.model_dump_json(indent=2))
            tmp_path.rename(event_path)

        if event.type == EventType.CONVERGED or event.type == EventType.STUCK:
            self._save_state(event.task_id, event)

        return str(event_path)

    def read_event(self, event_id: str) -> Event:
        event_path = self._event_dir / f"{event_id}.json"
        data = json.loads(event_path.read_text())
        return event_from_dict(data)

    def poll_inbox(self, agent: AgentName) -> list[Event]:
        inbox_dir = Path(".runtime/inbox") / str(agent.value)
        if not inbox_dir.exists():
            return []
        events = []
        for f in sorted(inbox_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                events.append(event_from_dict(data))
            except Exception:
                continue
        events.sort(key=lambda e: (e.timestamp, e.sequence))
        return events

    def get_task_events(self, task_id: str) -> list[Event]:
        events = []
        for f in sorted(self._event_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                if data.get("task_id") == task_id:
                    events.append(event_from_dict(data))
            except Exception:
                continue
        events.sort(key=lambda e: (e.timestamp, e.sequence))
        return events

    def replay_events(self, task_id: str) -> list[Event]:
        return self.get_task_events(task_id)

    def save_patch(self, task_id: str, diff_text: str, file_path: str) -> str:
        patch_path = self._patches_dir / f"{task_id}_{file_path.replace('/', '_')}.patch"
        lock = FileLock(str(patch_path) + ".lock", timeout=10, lifetime=300)
        with lock:
            patch_path.write_text(diff_text)
        return str(patch_path)

    def save_diff(self, task_id: str, diff_text: str) -> str:
        diff_path = self._diffs_dir / f"{task_id}.diff"
        diff_path.write_text(diff_text)
        return str(diff_path)

    def save_task_state(self, task_id: str, state: dict) -> str:
        state_path = self._tasks_dir / f"{task_id}.json"
        state_path.write_text(json.dumps(state, indent=2))
        return str(state_path)

    def _save_state(self, task_id: str, event: Event) -> str:
        state_path = self._state_dir / f"{task_id}.json"
        state_path.write_text(event.model_dump_json(indent=2))
        return str(state_path)
