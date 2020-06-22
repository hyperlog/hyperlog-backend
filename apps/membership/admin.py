from django.contrib import admin

from apps.membership.models import (
    StripeCustomer,
    StripeProduct,
    StripePrice,
    StripeSubscription,
)

admin.site.register(StripeCustomer)
admin.site.register(StripeProduct)
admin.site.register(StripePrice)
admin.site.register(StripeSubscription)
