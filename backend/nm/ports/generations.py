"""Availability of a captured source/practice generation at a serving boundary."""


class GenerationUnavailable(ValueError):
    """A bound generation changed, disappeared or lost its permission.

    Composition owns how the generation is measured. Callers own refusing a
    stale projection; they must not import a deployment's measurement adapter.
    """
