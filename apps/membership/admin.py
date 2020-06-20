from django.contrib import admin

from apps.membership.models import StripeProduct, StripePrice

admin.register(StripeProduct)
admin.register(StripePrice)
