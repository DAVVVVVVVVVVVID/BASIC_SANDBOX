from datetime import datetime

_MAX_LOG_SIZE = 20
_LOG: list[dict] = []


def append_log(
    entity_id: str,
    action_type: str,
    payload: dict,
    success: bool,
    reason: str | None,
    label: str | None = None,
) -> None:
    _LOG.append({
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "entityId":  entity_id,
        "type":      action_type,
        "payload":   payload,
        "success":   success,
        "reason":    reason,
        "label":     label,
    })
    if len(_LOG) > _MAX_LOG_SIZE:
        _LOG.pop(0)


def get_log() -> list[dict]:
    return list(_LOG)
