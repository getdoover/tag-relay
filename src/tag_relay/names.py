"""Deterministic name helpers for tag-relay.

Mirror tags and UI interaction names are derived from the destination
``app_key`` and tag name, so reordering the mappings array doesn't leave
orphaned tags or stale UI bindings pointing at the wrong row.
"""

import hashlib


def _slug(dest_app_key: str, dest_tag_name: str) -> str:
    return hashlib.sha1(
        f"{dest_app_key}/{dest_tag_name}".encode()
    ).hexdigest()[:8]


def mirror_key_for(dest_app_key: str, dest_tag_name: str) -> str:
    return f"mirror_{_slug(dest_app_key, dest_tag_name)}"


def variable_name_for(dest_app_key: str, dest_tag_name: str) -> str:
    return f"var_{_slug(dest_app_key, dest_tag_name)}"
