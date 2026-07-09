"""Per-instance agent autonomy: own backend, own context, private projection.

Each :class:`AgentInstance` is an autonomous participant: its OWN ``LlmBackend``
(own client, own key/provider -- R8), its OWN system prompt, and -- through a
:class:`Conversation` -- its OWN private view of the exchange. When instance A
talks to instance/server B, neither shares an agent object with the other; each
only ever sees its *projection* of the conversation (the utterances it sent or
received), never the peer's system prompt or internal reasoning. This is the
"pas d'instance d'agent commune aux deux" rule.

Deterministic (I4): projection is a pure function of the append-only utterance
log; a run driven by per-instance ``StubLlm``/``ReplayLlm`` is fully reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass

from .llm import LlmBackend, LlmDecision, Message, ToolSpec

# A recipient that every participant can read (a shared floor, e.g. a group chat
# manager). A directed recipient is read only by that instance and the sender.
BROADCAST = "*"


@dataclass(frozen=True)
class AgentInstance:
    """One autonomous agent instance. Its ``backend`` is exclusively its own.

    ``instance_id`` is anchored on the agent passport's ``agent_id`` (admission),
    so an instance is identifiable and stable across sessions. ``system`` is
    PRIVATE: it is never written to a shared conversation log, so no peer can read
    it -- isolation holds by construction, not by convention.
    """

    instance_id: str
    role: str
    system: str
    backend: LlmBackend
    provider: str = "stub"
    model: str = ""
    capability_scope: tuple[str, ...] = ()

    def decide(self, history: list[Message], tools: list[ToolSpec] | None = None) -> LlmDecision:
        """Decide the next step from THIS instance's private view + its own system.

        ``history`` must be the instance's projection of the conversation (see
        :meth:`Conversation.project`); the caller never passes another instance's
        view. The system prompt is the instance's own and is added here, so it
        cannot leak into any shared log."""
        return self.backend.decide(system=self.system, history=history, tools=tools or [])


@dataclass(frozen=True)
class Utterance:
    """One line spoken by ``sender`` to ``recipient`` (an ``instance_id`` or
    :data:`BROADCAST`). Content only -- never a system prompt or hidden state."""

    seq: int
    sender: str
    recipient: str
    content: str


class Conversation:
    """An ordered exchange between autonomous instances, keyed by a session.

    Holds a single append-only utterance log. Each instance reads ONLY its
    projection -- the utterances it sent or received -- as neutral ``Message``
    turns. No instance can read another's system prompt through this object;
    systems live on the :class:`AgentInstance` and are never appended here.
    """

    def __init__(self, session_id: str) -> None:
        if not session_id:
            raise ValueError("a Conversation requires a non-empty session_id")
        self.session_id = session_id
        self._log: list[Utterance] = []

    def append(self, *, sender: str, recipient: str, content: str) -> Utterance:
        if not sender:
            raise ValueError("an utterance requires a sender instance_id")
        u = Utterance(
            seq=len(self._log),
            sender=sender,
            recipient=recipient or BROADCAST,
            content=content,
        )
        self._log.append(u)
        return u

    @property
    def log(self) -> list[Utterance]:
        """A copy of the full log. The full log is an AUDIT view (the tracker /
        an auditor), never what an instance decides on -- instances use
        :meth:`project`."""
        return list(self._log)

    def _visible_to(self, instance_id: str, u: Utterance) -> bool:
        return u.sender == instance_id or u.recipient in (instance_id, BROADCAST)

    def project(self, instance_id: str) -> list[Message]:
        """The PRIVATE view of ``instance_id``.

        Only the utterances it sent or received, as ``Message`` turns (its own ->
        ``assistant``, peers' -> ``user``). Never any instance's system prompt,
        never an utterance directed between two other instances. Pure and
        deterministic (I4)."""
        out: list[Message] = []
        for u in self._log:
            if not self._visible_to(instance_id, u):
                continue
            role = "assistant" if u.sender == instance_id else "user"
            out.append(Message(role=role, content=u.content))
        return out

    def participants(self) -> list[str]:
        """Distinct instance ids seen in the log, in first-appearance order."""
        ids: list[str] = []
        for u in self._log:
            for x in (u.sender, u.recipient):
                if x and x != BROADCAST and x not in ids:
                    ids.append(x)
        return ids
