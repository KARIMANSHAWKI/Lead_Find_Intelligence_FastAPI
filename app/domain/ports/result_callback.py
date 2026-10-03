from abc import ABC, abstractmethod


class ResultCallbackPort(ABC):
    @abstractmethod
    async def send(self, url: str, token: str, payload: dict) -> bool:
        """Deliver a terminal result to the authorized Laravel callback."""
        raise NotImplementedError
