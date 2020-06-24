import logging
from datetime import datetime

import graphene
import stripe
from graphql_jwt.decorators import login_required

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.base.utils import create_model_object, get_error_messages
from apps.membership.models import (
    StripeCustomer,
    StripePrice,
    StripeSubscription,
)


logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_API_KEY


class CreateStripeCustomer(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    class Arguments:
        description = graphene.String()

    @login_required
    def mutate(self, info, **kwargs):
        user = info.context.user
        email = user.email
        try:
            validate_email(email)
        except ValidationError as e:
            errors = get_error_messages(e)
            return CreateStripeCustomer(success=False, errors=errors)

        description = kwargs.get("description", "")
        metadata = {"user_id": user.id}

        if StripeCustomer.objects.filter(user=user).exists():
            error = "A Stripe Customer is already associated with this user"
            return CreateStripeCustomer(success=False, errors=[error])

        customer = stripe.Customer.create(
            email=email,
            description=description,
            metadata=metadata,
            name=user.full_name,
        )

        create_result = create_model_object(
            StripeCustomer,
            id=customer.id,
            email=customer.email,
            description=customer.description or "",
            metadata=customer.metadata,
            user=user,
        )

        return CreateStripeCustomer(
            success=create_result.success, errors=create_result.errors
        )


class CreateStripeSubscription(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    class Arguments:
        payment_method_id = graphene.String(required=True)
        price_id = graphene.String(required=True)

    @login_required
    def mutate(self, info, payment_method_id, price_id):
        user = info.context.user
        customer = user.stripe_customer

        try:
            # Attach payment method to customer
            stripe.PaymentMethod.attach(
                payment_method_id, customer=customer.id
            )

            # Set default payment method on customer
            stripe.Customer.modify(
                customer.id,
                invoice_settings={"default_payment_method": payment_method_id},
            )

            # Create subscription
            subscription = stripe.Subscription.create(
                customer=customer.id,
                items=[{"price": price_id}],
                expand=["latest_invoice.payment_intent"],
            )

        except Exception as e:
            return CreateStripeSubscription(
                success=False, errors=get_error_messages(e)
            )

        create_result = create_model_object(
            StripeSubscription,
            id=subscription.id,
            current_period_start=datetime.fromtimestamp(
                subscription.current_period_start
            ),
            current_period_end=datetime.fromtimestamp(
                subscription.current_period_end
            ),
            status=subscription.status,
            customer=customer,
            price=StripePrice.objects.get(price_id),
        )

        return CreateStripeSubscription(
            create_result.success, errors=create_result.errors
        )


class RetryStripeSubscription(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)
    invoice = graphene.String()  # JSON-encoded string representing invoice

    class Arguments:
        payment_method_id = graphene.String(required=True)
        invoice_id = graphene.String(required=True)

    @login_required
    def mutate(self, info, payment_method_id, invoice_id):
        user = info.context.user
        customer = user.stripe_customer

        try:
            stripe.PaymentMethod.attach(
                payment_method_id, customer=customer.id
            )
            # Set default payment method
            stripe.Customer.modify(
                customer.id,
                invoice_settings={"default_payment_method": payment_method_id},
            )

            invoice = stripe.Invoice.retrieve(
                invoice_id, expand=["payment_intent"]
            )
            return RetryStripeSubscription(success=True, invoice=str(invoice))

        except Exception as e:
            return RetryStripeSubscription(
                success=False, errors=get_error_messages(e)
            )


class CancelStripeSubscription(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)
    subscription = graphene.String()  # JSON-encoded deleted subscription

    @login_required
    def mutate(self, info):
        user = info.context.user
        customer = user.stripe_customer

        if hasattr(customer, "subscription"):
            subscription = customer.subscription
        else:
            error = "No associated subscription found"
            return CancelStripeSubscription(success=False, errors=[error])

        try:
            deleted_subscription = stripe.Subscription.delete(subscription.id)
        except Exception as e:
            return CancelStripeSubscription(
                success=False, errors=get_error_messages(e)
            )

        subscription.delete()
        return CancelStripeSubscription(
            success=True, subscription=str(deleted_subscription)
        )


class Mutation(graphene.ObjectType):
    create_stripe_customer = CreateStripeCustomer.Field()
    create_stripe_subscription = CreateStripeSubscription.Field()
    retry_stripe_subscription = RetryStripeSubscription.Field()
    cancel_stripe_subscription = CancelStripeSubscription.Field()
