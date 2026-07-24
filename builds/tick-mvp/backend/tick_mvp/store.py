from tick_mvp.infrastructure.memory_store import MemoryStore, QuoteRecord, StoreConflict, StoreNotFound, TradeBundle

__all__ = ["MemoryStore", "QuoteRecord", "SQLAlchemyStore", "StoreConflict", "StoreNotFound", "TradeBundle"]


def __getattr__(name: str):
    if name == "SQLAlchemyStore":
        from tick_mvp.infrastructure.sqlalchemy_store import SQLAlchemyStore

        return SQLAlchemyStore
    raise AttributeError(name)
