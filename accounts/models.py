from django.contrib.auth.models import AbstractUser

from wimm.base_models import BaseModel


class CustomUser(BaseModel, AbstractUser):
    pass

    def __str__(self):
        return self.username
