"""Бот ZHIDAO для мессенджера MAX.

Отдельный процесс. Он **не открывает базу**: всё, что меняет состояние,
уходит HTTP-запросом в API V4 под своей служебной учёткой. Это не стилевое
предпочтение, а прямое следствие аварии 2026-06-09, когда бот сезона 1 был
вторым писателем в ту же SQLite и держал write-lock через сетевые вызовы
Telegram — запросы к API вставали на 27–1463 секунды. Правило записано в
CLAUDE.md; здесь оно исполняется.
"""

from .max_api import MaxApiError, MaxBotApi
from .backend import BackendError, V4Backend

__all__ = ["MaxBotApi", "MaxApiError", "V4Backend", "BackendError"]
