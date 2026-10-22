"""Join installed ALAS task names to fresh game-owned activity identities.

This is identity lookup, not task selection. Dates and positions are never
interpreted as game IDs; existing observation/input ports still own each action.
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from .errors import SemanticGateClosed, SemanticRaidUnavailable


@lru_cache(maxsize=8)
def _read_labels(path: str, stamp: int, size: int) -> Mapping[str, str]:
    del stamp, size
    with Path(path).open(encoding="utf-8") as stream:
        labels = json.load(stream)["Campaign"]["Event"]
    if not isinstance(labels, dict):
        raise ValueError("Campaign.Event is not a mapping")
    return labels


def installed_event_title(event: str, *, package: str) -> str:
    """Read the locale for the actual game from the loaded ALAS installation.

    Never search neighbouring checkouts or import/execute an unselected task.
    A missing translation affects only the requested new activity mapping.
    """
    locales = {
        "com.bilibili.azurlane": ("zh-CN", "档案 "),
        "com.YoStarEN.AzurLane": ("en-US", "archives "),
        "com.YoStarJP.AzurLane": ("ja-JP", ""),
        "com.hkmanjuu.azurlane.gp": ("zh-TW", "檔案 "),
    }
    try:
        locale, prefix = locales[package]
        paths = []
        for name in ("module.config.config", "module.config.server", "module.config"):
            origin = getattr(sys.modules.get(name), "__file__", None)
            if origin:
                candidate = Path(origin).resolve().parent / "i18n" / (locale + ".json")
                if candidate not in paths and candidate.is_file():
                    paths.append(candidate)
        if len(paths) != 1:
            raise ValueError("loaded ALAS locale source is absent or ambiguous")
        path = paths[0]
        stat = path.stat()
        title = _read_labels(str(path), stat.st_mtime_ns, stat.st_size)[event]
        if not isinstance(title, str) or not title.strip():
            raise ValueError("task title is absent")
        title = title.strip()
        if event.startswith("war_archives_") and prefix:
            if not title.startswith(prefix):
                raise ValueError("archive title prefix is absent")
            title = title[len(prefix):]
        return title
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise SemanticGateClosed(
            f"activity identity mapping for {event!r} needs its installed ALAS "
            "game-locale title; independent tasks remain available"
        ) from exc


def identity_records(snapshot: Mapping, family: str, event: str) -> tuple[Mapping, ...]:
    """Consume only this optional identity family from the validated UI frame."""
    identity = snapshot.get("activity_identity")
    if (not isinstance(identity, Mapping) or type(identity.get("status")) is not int
            or identity.get("status") != 1 or type(identity.get("stack_balanced")) not in (bool, int)
            or identity.get("stack_balanced") != 1):
        raise SemanticGateClosed(f"activity identity mapping for {event!r} requires the game Lua identity reader")
    group = identity.get(family)
    if (not isinstance(group, Mapping) or type(group.get("status")) is not int
            or group.get("status") != 1 or type(group.get("truncated")) not in (bool, int)
            or group.get("truncated") not in (False, 0)):
        raise SemanticGateClosed(f"{family} identity mapping for {event!r} is incomplete; reopen the activity page after game tables load")
    records = group.get("records")
    if not isinstance(records, (list, tuple)):
        raise SemanticGateClosed(f"{family} identity mapping for {event!r} has malformed records")
    if type(group.get("expected_count")) is not int or group["expected_count"] != len(records):
        raise SemanticGateClosed(f"{family} identity mapping for {event!r} has an incomplete record count")
    ids = set()
    for record in records:
        if not isinstance(record, Mapping) or type(record.get("id")) is not int or record["id"] <= 0 or record["id"] in ids:
            raise SemanticGateClosed(f"{family} identity mapping for {event!r} has malformed or duplicate IDs")
        ids.add(record["id"])
    return tuple(records)


def archive_identity(snapshot: Mapping, event: str, package: str, reviewed_identity=None) -> tuple[str, str]:
    records = identity_records(snapshot, "archives", event)
    try:
        title = installed_event_title(event, package=package)
    except SemanticGateClosed:
        if reviewed_identity is None:
            raise
        title = None
    matches = []
    for record in records:
        name = record.get("name")
        if not isinstance(name, str) or not name:
            raise SemanticGateClosed("archive identity has no game activity name")
        # A schema suffix, not a fuzzy title match or a per-event alias table.
        if package == "com.bilibili.azurlane" and name.endswith("常驻复刻"):
            name = name[:-4]
        if name == title:
            matches.append(record)
    if not matches and reviewed_identity is not None:
        # Older game rows sometimes abbreviate the title (e.g. the ship name).
        # Retain their reviewed semantic asset association, but take the current
        # category from the actual record. This is never used for a new folder.
        matches = [record for record in records if record.get("bg") == reviewed_identity[1]]
    if len(matches) != 1:
        raise SemanticGateClosed(f"war archives identity mapping for {event!r} is absent or ambiguous in the current game")
    record = matches[0]
    kind = record.get("activity_type")
    category = {1: "ex", 2: "sp"}.get(kind) if type(kind) is int else None
    sprite = record.get("bg")
    if category is None or not isinstance(sprite, str) or not sprite or "/" in sprite or "\\" in sprite:
        raise SemanticGateClosed(f"war archives identity mapping for {event!r} has an unsupported category/banner")
    return category, sprite


def raid_identity(snapshot: Mapping, event: str | None = None) -> tuple[str, str]:
    """Use the game's release mark and server-owned ActivityProxy membership.

    A matching date alone is insufficient: the observer joins the same numeric
    ID in ActivityProxy.data to the boss activity config. Layout identity remains
    separate, and the actual typed controls must still pass their existing checks.
    """
    records = identity_records(snapshot, "raids", event or "current Raid")
    matches = []
    for record in records:
        mark = record.get("mark")
        if type(mark) is not int or mark <= 0 or type(record.get("activity_type")) is not int:
            raise SemanticGateClosed("Raid identity mapping has a malformed game activity mark/type")
        key = "raid_" + str(mark)
        if event is None or key == event:
            matches.append((key, record))
    if not matches:
        raise SemanticRaidUnavailable(
            f"Raid identity mapping for {event!r} is absent in the current game; "
            "re-enter when the configured activity is available")
    if len(matches) != 1:
        raise SemanticGateClosed(f"Raid identity mapping for {event!r} is ambiguous in the current game")
    key, record = matches[0]
    page_core = record.get("page_core")
    if not isinstance(page_core, str):
        raise SemanticGateClosed(f"Raid identity mapping for {key!r} has a malformed typed layout")
    layout = {"ActivityBossAmatsukazeUI": "amatsukaze"}.get(page_core)
    if layout is None:
        raise SemanticRaidUnavailable(
            f"Raid identity mapping for {key!r} uses an unsupported typed layout: "
            f"{record.get('page_core')!r}; re-enter after this layout has a reviewed typed port")
    return key, layout
