"""What the web server and the step worker share when the steps run in a worker process of their own (plan AN.48, piece 48f4;
owner decision D167). Everything carrying the advocate's words or NM's answer is sealed by the adapter."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class StepSharePort(Protocol):
    def ask(self, advocate_id: str, turn_id: str, asked: dict) -> int:
        """A step the web server takes, for the worker. Returns its number."""
        ...

    def take(self) -> list:
        """The worker takes every step not yet taken, oldest first."""
        ...

    def answer(self, number: int, answered: dict) -> None:
        """What that step answered, for the web server."""
        ...

    def answered(self, number: int):
        """What that step answered, or None while it waits or works."""
        ...

    def latest(self, advocate_id: str, turn_id: str):
        """The newest step of that turn: (number, done), or None."""
        ...

    def control(self, advocate_id: str, turn_id: str, kind: str, asked) -> int:
        """What is asked of a step at work: Stop, Steer, answers, what is typed meanwhile."""
        ...

    def controls(self) -> list:
        """The worker reads what is asked, oldest first."""
        ...

    def verdict(self, number: int, answered: dict) -> None:
        """The worker's word on what was asked."""
        ...

    def verdict_of(self, number: int):
        """That word, or None while the worker has not said it."""
        ...

    def show_window(self, advocate_id: str, turn_id: str, view: dict) -> None:
        """NM's open questions on a turn, as the advocate's page reads them."""
        ...

    def close_window(self, advocate_id: str, turn_id: str) -> None:
        ...

    def window(self, advocate_id: str, turn_id: str):
        ...

    def close_windows(self) -> None:
        ...

    def put_progress(self, advocate_id: str, turn_id: str, row: dict) -> None:
        """A turn's progress row: stage names, counts and times only."""
        ...

    def progress(self, advocate_id: str, turn_id: str):
        ...

    def all_progress(self) -> list:
        ...

    def beat(self, name: str, *, waiting: int, working: int) -> None:
        """The worker is there, with so many steps waiting and at work."""
        ...

    def workers(self) -> list:
        ...

    def forget(self, older_than: float) -> None:
        """What was answered long ago is let go."""
        ...
