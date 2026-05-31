from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    tg = models.CharField(max_length=64, null=True, blank=True)
    has_loyalty = models.BooleanField(default=False)

    def __str__(self) -> str:
        name = (self.get_full_name() or "").strip()
        if name and self.phone:
            return f"{name} ({self.phone})"
        if name:
            return name
        if self.phone:
            return self.phone
        return self.get_username()
