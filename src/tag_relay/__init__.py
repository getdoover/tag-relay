from typing import Any

from pydoover.processor import run_app

from .app_config import TagRelayConfig
from .application import TagRelayApplication


def handler(event: dict[str, Any], context):
    """Lambda handler entry point."""
    TagRelayConfig.clear_elements()
    run_app(TagRelayApplication(), event, context)
