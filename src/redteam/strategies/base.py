"""Base classes and registry for attack strategy families."""
from __future__ import annotations


class Strategy:
    """A single-turn strategy renders one prompt from the goal."""

    name: str = ""
    description: str = ""
    is_multi_turn: bool = False

    def render(self, goal: str) -> str | list[str]:
        """Return a prompt (str) or a multi-turn script (list of str)."""
        raise NotImplementedError

    def payload(self, goal: str) -> str | list[str]:
        return self.render(goal)

    def payload_messages(self, goal: str) -> list[dict] | None:
        """Optional full message list (e.g. forged system role).

        Return None by default: the runner then uses render()/payload().
        Strategies that need multi-role payloads (system shadowing) override
        this and the runner sends via send_history().
        """
        return None


_REGISTRY: dict[str, type[Strategy]] = {}


def register(cls: type[Strategy]) -> type[Strategy]:
    _REGISTRY[cls.name] = cls
    return cls


def get_strategy(name: str) -> Strategy:
    _ensure_loaded()
    return _REGISTRY[name]()


def list_strategies() -> list[str]:
    _ensure_loaded()
    return sorted(_REGISTRY)


def _ensure_loaded() -> None:
    # Import for side effects (registration). Kept local to avoid cycles.
    from redteam.strategies import families    # noqa: F401
    from redteam.strategies import pliny       # noqa: F401
    from redteam.strategies import v4_families  # noqa: F401
    from redteam import families_v3            # noqa: F401


def resolve_stack(spec: str, goal: str) -> str | list[str]:
    """Compose a `+`-joined stack, e.g. 'godmode+refusal_suppression+mutate:leetspeak'.

    Single-turn families wrap the current payload; mutate entries transform it
    (mutation always applies last-child-first: read left→right as pipelining).
    Multi-turn members of a stack are not allowed (ambiguity) → KeyError-safe:
    raises ValueError if a multi-turn family appears anywhere but is consumed.
    """
    _ensure_loaded()
    parts = [p.strip() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError("empty stack spec")

    # The final turn-provider: use the LAST non-mutate family as the carrier
    # (carriers like godmode/reference frames embed the goal text), and apply
    # mutate transforms to the goal text before embedding.
    mutators = [p for p in parts if p.startswith("mutate:")]
    carriers = [p for p in parts if not p.startswith("mutate:")]
    if not carriers:
        # pure mutation chain: wrap in a minimal decode-and-comply frame
        carriers = ["direct"]

    working_goal = goal
    for m in mutators:
        strategy = get_strategy(m)
        rendered = strategy.render(working_goal)
        # mutation strategies transform the goal text itself; recover payload
        # by locating the transformed goal inside the rendered wrapper.
        payload = _extract_mutated(rendered, working_goal)
        if not payload:
            raise ValueError(f"mutator {m} destroyed the goal text")
        working_goal = payload

    carrier = get_strategy(carriers[-1])
    if carrier.is_multi_turn:
        # apply remaining carriers as pre-amble injection is ill-defined for
        # multi-turn: reject explicit multi-carrier-stacks containing them
        if len(parts) > 1:
            raise ValueError(
                f"{carrier.name} is multi-turn and cannot be stacked"
            )
        return carrier.render(working_goal)

    # Fold remaining single-turn carriers inside-out: each earlier family's
    # render feeds the next as the "goal", so directives accumulate.
    payload = working_goal
    for name in carriers:
        s = get_strategy(name)
        payload = s.render(payload)
    return payload


def _extract_mutated(rendered: str, original_goal: str) -> str | None:
    """Recover the mutated goal from a mutate-family's full rendered prompt.

    Mutators render '(wrapper + payload)'; for invisible encodings the wrapper
    contains the payload. Simplest robust approach: ask the encoder to encode
    the goal directly and find that string inside the render.
    """
    from redteam.encoders import ENCODERS
    variant = None
    for name, fn in ENCODERS.items():
        if f"mutate:{name}" and rendered and fn(original_goal) in rendered:
            variant = (name, fn)
            break
    if variant:
        return variant[1](original_goal)
    return None