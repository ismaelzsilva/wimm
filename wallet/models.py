from django.contrib.auth import get_user_model
from django.db import models

from wimm.base_models import BaseModel

User = get_user_model()


class Wallet(BaseModel):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wallets")
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name
