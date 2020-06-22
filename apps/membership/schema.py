import graphene
import stripe
from graphql_jwt.decorators import login_required

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.base.utils import create_model_object, get_error_messages
from apps.membership.models import StripeCustomer

stripe.api_key = settings.STRIPE_API_KEY


class CreateStripeCustomer(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    class Arguments:
        email = graphene.String(required=True)
        description = graphene.String()

    @login_required
    def mutate(self, info, **kwargs):
        user = info.context.user
        email = kwargs.get("email")
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


class Mutation(graphene.ObjectType):
    create_stripe_customer = CreateStripeCustomer.Field()
