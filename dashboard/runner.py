import asyncio
import sys
import threading
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Settings
from src.data import create_data_provider
from src.engine import TradingEngine

_engine_thread = None
_lock = threading.Lock()


class EngineThread(threading.Thread):
    def __init__(self, settings: Settings, strategy_name: str, interval: int = 10):
        super().__init__(daemon=True)
        self.settings = settings
        self.strategy_name = strategy_name
        self.interval = interval
        self.loop = None
        self.engine = None
        self.exception = None

    def run(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            provider = create_data_provider(
                mode=self.settings.trading_mode.value,
                api_key=self.settings.kite_api_key,
                access_token=self.settings.kite_access_token,
            )
            self.engine = TradingEngine(self.settings, provider, strategy_name=self.strategy_name)
            self.loop.run_until_complete(self.engine.run(interval_seconds=self.interval))
        except Exception as e:
            self.exception = e
        finally:
            if self.loop:
                try:
                    self.loop.close()
                except Exception:
                    pass

    def stop(self):
        if self.engine:
            self.engine.stop()


def start_engine(settings: Settings, strategy_name: str, interval: int = 10) -> bool:
    global _engine_thread
    with _lock:
        if is_engine_running():
            return False
        _engine_thread = EngineThread(settings, strategy_name, interval)
        _engine_thread.start()
        return True


def stop_engine() -> bool:
    global _engine_thread
    with _lock:
        if not is_engine_running():
            return False
        _engine_thread.stop()
        _engine_thread.join(timeout=3)
        _engine_thread = None
        return True


def is_engine_running() -> bool:
    global _engine_thread
    return _engine_thread is not None and _engine_thread.is_alive()
