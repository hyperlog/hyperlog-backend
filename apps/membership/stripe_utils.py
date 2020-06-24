import logging
from datetime import datetime

from apps.membership.models import (
    StripeProduct,
    StripePrice,
    StripeSubscription,
)

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


def save_product_to_db(stripe_product):
    """
    Takes a stripe.Product as argument and attempts to save it to the database
    """
    id = stripe_product.id
    if StripeProduct.objects.filter(id=id).exists():
        logger.warning("Product %s already exists" % id)
        return

    db_product = StripeProduct(
        id=id,
        active=stripe_product.active,
        name=stripe_product.name,
        description=stripe_product.description or "",
    )
    if stripe_product.metadata:
        db_product.metadata = stripe_product.metadata

    db_product.full_clean()
    db_product.save()


def save_price_to_db(stripe_price):
    """
    Takes a stripe.Product as argument and attempts to save it to the database
    """
    id = stripe_price.id
    if StripePrice.objects.filter(id=id).exists():
        logger.warning("Price %s already exists" % id)

    try:
        related_product = StripeProduct.objects.get(id=stripe_price.product)
    except StripeProduct.DoesNotExist:
        logger.error(
            "Cannot save price %(price_id)s to database. "
            "Related product %(product_id)s does not exist"
            % {
                "price_id": stripe_price.id,
                "product_id": stripe_price.product,
            }
        )
        raise

    db_price = StripePrice(
        id=id,
        active=stripe_price.active,
        currency=stripe_price.currency,
        nickname=stripe_price.nickname or "",
        product=related_product,
        type=stripe_price.type,
        unit_amount=stripe_price.unit_amount,
    )

    if stripe_price.metadata:
        db_price.metadata = stripe_price.metadata

    if stripe_price.recurring:
        db_price.recurring = stripe_price.recurring

    db_price.full_clean()
    db_price.save()
