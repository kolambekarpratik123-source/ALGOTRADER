"""Executor factory."""

from src.execution.paper import PaperExecutor


def create_executor(mode: str, api_key: str = "", access_token: str = ""):
    if mode == "live" and api_key and access_token:
        try:
            from src.execution.kite import KiteExecutor

            return KiteExecutor(api_key, access_token)
        except Exception:
            pass
    return PaperExecutor()
