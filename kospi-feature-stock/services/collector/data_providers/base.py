from abc import ABC, abstractmethod


class DataProvider(ABC):
    @abstractmethod
    async def get_daily_bars(self, code: str, days: int) -> list[dict]: ...

    @abstractmethod
    async def get_stock_list(self) -> list[dict]: ...

    @abstractmethod
    async def get_market_index(self) -> dict: ...

    @abstractmethod
    async def get_supply_demand(self, code: str, date: str) -> dict | None: ...

    @property
    @abstractmethod
    def is_realtime(self) -> bool: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
