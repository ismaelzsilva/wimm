import uuid
from datetime import datetime

from django.db import models
from django.utils.functional import (
    cached_property,
)


class BaseModel(models.Model):
    uuid = models.UUIDField(default=uuid.uuid7, primary_key=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @cached_property
    def created_at(self):
        return datetime.fromtimestamp(self.uuid.time / 1000)
