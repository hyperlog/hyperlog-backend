import logging
from datetime import datetime

from apps.membership.models import StripePrice, StripeSubscription

logger = logging.getLogger(__name__)


def update_subscription_from_db(subscription_id, stripe_subscription):
    """
    Updates the local StripeSubscription according to the one fetched from
    Stripe
    """
    subscription_from_db = StripeSubscription.objects.get(id=subscription_id)

    new_period_end = datetime.fromtimestamp(
        stripe_subscription.current_period_end
    )
    if new_period_end > subscription_from_db.current_period_end:
        tdelta = new_period_end - subscription_from_db.current_period_end
        logger.info(
            "Subscription %(id)s period extended by %(days)i days"
            % {"id": subscription_id, "days": tdelta.days}
        )

    subscription_from_db.current_period_start = datetime.fromtimestamp(
        stripe_subscription.current_period_start
    )
    subscription_from_db.current_period_end = new_period_end

    if subscription_from_db.status != stripe_subscription.status:
        logger.info(
            "Status of subscription %(id)s changed from %(old)s to %(new)s"
            % {
                "id": subscription_id,
                "old": subscription_from_db.status,
                "new": stripe_subscription.status,
            }
        )
        subscription_from_db.status = stripe_subscription.status

    # Update subscribed package
    new_price_id = stripe_subscription.items.data[0].id
    if subscription_from_db.price.id != new_price_id:
        logger.info(
            "Subscription %(id)s changed Price from %(old)s to %(new)s"
            % {
                "id": subscription_id,
                "old": subscription_from_db.price.id,
                "new": new_price_id,
            }
        )
        subscription_from_db.price = StripePrice.objects.get(id=new_price_id)

    subscription_from_db.full_clean()
    subscription_from_db.save()
