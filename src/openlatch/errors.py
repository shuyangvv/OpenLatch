class OpenLatchError(Exception):
    """Base error for configuration and fit failures."""


class PackError(OpenLatchError):
    """Pack YAML is illegal or an unpinned model is locked."""


class PolicyError(OpenLatchError):
    """Policy JSON is illegal or does not bind to its Pack."""


class AnswerError(OpenLatchError):
    """A single answer cannot yield a signal."""


class NotEnoughLabels(OpenLatchError):
    def __init__(self, n: int, min_n: int) -> None:
        super().__init__(f"not enough labels: n={n} < min_n={min_n}")
        self.n = n
        self.min_n = min_n
