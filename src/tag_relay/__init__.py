from typing import Any

from pydoover.processor import run_app

from .application import TagRelayApplication


def handler(event: dict[str, Any], context):
    """Lambda handler entry point."""
    # NOTE: no TagRelayConfig.clear_elements() call — that pattern is for
    # __init__-based schemas (re-adds elements each instantiation). Our
    # schema is class-level declarative; clearing would wipe the element
    # map permanently for the remaining life of the sandbox, causing
    # every config field to be loaded as a plain ConfigElement.
    run_app(TagRelayApplication(), event, context)
