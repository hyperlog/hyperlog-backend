import stripe

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.membership.stripe_utils import update_subscription_from_db

STRIPE_WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET
stripe.api_key = settings.STRIPE_API_KEY


@require_POST
@csrf_exempt
def webhook(request):
    payload = request.body
    sig_header = request.META["HTTP_STRIPE_SIGNATURE"]

    # Validate request
    try:
        event = stripe.Webhooks.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        # invalid payload
        return HttpResponse(status=400)
    except stripe.errors.SignatureVerificationError:
        # invalid signature
        return HttpResponse(status=400)

    # Handle event
    if event.type == "customer.subscription.updated":
        subscription = event.data.object
        update_subscription_from_db(subscription.id, subscription)
        return HttpResponse(status=200)
    else:
        return HttpResponse(status=400)
