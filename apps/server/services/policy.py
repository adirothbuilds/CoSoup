from ..config import Settings
from ..persistence.models import Policy


def effective(settings, db):
    row = db.get(Policy, "storage")
    if row is None:
        return settings
    values = settings.model_dump()
    for key, value in row.values.items():
        if key == "limits":
            values[key] = {**values[key], **value}
        else:
            values[key] = value
    return Settings(**values)
