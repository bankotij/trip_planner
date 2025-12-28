from django.db import models


class FuelStation(models.Model):
    opis_truckstop_id = models.CharField(max_length=255, null=True, blank=True)
    truckstop_name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=255)
    state = models.CharField(max_length=255)
    retail_price = models.DecimalField(max_digits=10, decimal_places=3)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["state", "city"]),
            models.Index(fields=["retail_price"]),
        ]

    def __str__(self):
        return f"{self.truckstop_name} - {self.city}, {self.state}"
