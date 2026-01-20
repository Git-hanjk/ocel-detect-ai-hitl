from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional, Tuple


def _extract_links(raw: Optional[str]) -> List[Tuple[str, Optional[str]]]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    links: List[Tuple[str, Optional[str]]] = []
    if isinstance(payload, dict):
        linked = payload.get("linked_object_ids") or payload.get("ocel_objects")
        if isinstance(linked, list) and linked and isinstance(linked[0], str):
            links.extend([(obj_id, None) for obj_id in linked])
        objects = payload.get("objects")
        if isinstance(objects, list):
            for item in objects:
                if isinstance(item, str):
                    links.append((item, None))
                elif isinstance(item, dict):
                    obj_id = item.get("id") or item.get("ocel_id")
                    qualifier = item.get("qualifier") or item.get("ocel_qualifier")
                    if obj_id:
                        links.append((obj_id, qualifier))
    return links


def create_derived_event_object(conn, output_conn=None) -> None:
    if output_conn is None:
        output_conn = conn

    output_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_event_object (
            event_id TEXT,
            object_id TEXT,
            qualifier TEXT
        )
        """
    )
    output_conn.execute("DELETE FROM derived_event_object")

    event_object_map: Dict[str, List[Tuple[str, Optional[str]]]] = {}
    for event_id, object_id, qualifier in conn.execute(
        "SELECT ocel_event_id, ocel_object_id, ocel_qualifier FROM event_object"
    ).fetchall():
        event_object_map.setdefault(event_id, []).append((object_id, qualifier))

    inserts: List[Tuple[str, str, Optional[str]]] = []
    rows = conn.execute("SELECT event_id, raw FROM v_events_unified").fetchall()
    for event_id, raw in rows:
        seen = set()
        for object_id, qualifier in event_object_map.get(event_id, []):
            key = (event_id, object_id, qualifier)
            if key not in seen:
                seen.add(key)
                inserts.append((event_id, object_id, qualifier))
        for object_id, qualifier in _extract_links(raw):
            key = (event_id, object_id, qualifier)
            if key not in seen:
                seen.add(key)
                inserts.append((event_id, object_id, qualifier))

    output_conn.executemany(
        "INSERT INTO derived_event_object (event_id, object_id, qualifier) VALUES (?, ?, ?)",
        inserts,
    )
    output_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_derived_event_object_event ON derived_event_object(event_id)"
    )
    output_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_derived_event_object_object ON derived_event_object(object_id)"
    )
    output_conn.commit()
