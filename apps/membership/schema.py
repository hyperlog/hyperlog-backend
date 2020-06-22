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
        email = kwargs.get("email")
        try:
            validate_email(email)
        except ValidationError as e:
            errors = get_error_messages(e)
            return CreateStripeCustomer(success=False, errors=errors)

        description = kwargs.get("description")
        metadata = {"user_id": info.context.user.id}
        customer = stripe.Customer.create(
            email=email, description=description, metadata=metadata
        )

        create_result = create_model_object(
            StripeCustomer,
            id=customer.id,
            email=customer.email,
            description=customer.description,
            metadata=customer.metadata,
            user=info.context.user,
        )

        return CreateStripeCustomer(
            success=create_result.success, errors=create_result.errors
        )
