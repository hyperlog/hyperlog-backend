# from datetime import timedelta
import logging

import graphene
import graphql_jwt
from graphene_django import DjangoObjectType
from graphql_jwt.decorators import login_required
from graphql_jwt.utils import jwt_decode  # , jwt_encode
from jwt.exceptions import InvalidTokenError

from django.contrib.auth import get_user_model, logout
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.utils import Error as DjangoDBError
from django.utils import timezone

from apps.base.utils import get_error_messages, get_model_object
from apps.users.models import User
from apps.users.utils import (
    delete_user as delete_user_util,
    create_user as create_user_util,
)

logger = logging.getLogger(__name__)


class UserType(DjangoObjectType):
    class Meta:
        model = User
        only_fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "registered_at",
            "is_enrolled_for_mails",
            # From relations
            "profiles",
            "notifications",
            "widget",
        ]


class Query(graphene.ObjectType):
    user = graphene.Field(UserType, id=graphene.String(required=True))
    this_user = graphene.Field(UserType)

    @staticmethod
    def resolve_user(cls, info, **kwargs):
        return User.objects.get(id=kwargs.get("id"))

    @staticmethod
    @login_required
    def resolve_this_user(cls, info, **kwargs):
        if info.context.user.is_authenticated:
            return info.context.user


class Login(graphql_jwt.JSONWebTokenMutation):
    user = graphene.Field(UserType)

    @classmethod
    def resolve(cls, root, info, **kwargs):
        return cls(user=info.context.user)


class Register(GenericResultMutation):
    login = graphene.Field(Login)

    class Arguments:
        email = graphene.String(required=True)
        username = graphene.String(required=True)
        password = graphene.String(required=True)
        first_name = graphene.String(required=True)
        last_name = graphene.String(required=True)

    def mutate(self, info, email, username, password, first_name, last_name):
        user_creation = create_user_util(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

        if user_creation.success is True:
            return Register(
                success=True,
                login=Login.mutate(
                    self, info, username=username, password=password
                ),
            )
        else:
            return Register(
                success=user_creation.success, errors=user_creation.errors
            )


class IsUsernameValid(GenericResultMutation):
    """Checks if a username is valid and can be registerd

    Using the Mutation type so as to accommodate errors if any
    """

    class Arguments:
        username = graphene.String(required=True)

    def mutate(self, info, **kwargs):
        try:
            User._meta.get_field(User.USERNAME_FIELD).clean(
                kwargs.get("username"), User
            )
        except ValidationError as e:
            return IsUsernameValid(success=False, errors=get_error_messages(e))

        if User.objects.filter(username=kwargs.get("username")).exists():
            # Heads up: Removing the unique field from the error_messages
            # attribute in the model definition will result in unrendered
            # error messages like '%(model_name)s already has a ...'
            err_msg = User._meta.get_field("username").error_messages["unique"]
            return IsUsernameValid(success=False, errors=[err_msg])

        return IsUsernameValid(success=True)


class IsEmailValid(GenericResultMutation):
    """Checks if an email address is valid and can be registered

    Using the Mutation type so as to accommodate errors if any
    """

    class Arguments:
        email = graphene.String(required=True)

    def mutate(self, info, **kwargs):
        try:
            User._meta.get_field(User.EMAIL_FIELD).clean(
                kwargs.get("email"), User
            )
        except ValidationError as e:
            return IsEmailValid(success=False, errors=get_error_messages(e))

        if User.objects.filter(email=kwargs.get("email")):
            # Heads up: Removing the unique field from the error_messages
            # attribute in the model definition will result in unrendered
            # error messages like '%(model_name)s already has a ...'
            err_msg = User._meta.get_field("email").error_messages["unique"]
            return IsEmailValid(success=False, errors=[err_msg])

        return IsEmailValid(success=True)


class Logout(GenericResultMutation):
    """ Mutation to logout a user """

    def mutate(self, info):
        logout(info.context)
        return Logout(success=True)


class UpdateUser(GenericResultMutation):
    """Mutation to update user's profile details"""

    class Arguments:
        email = graphene.String()
        first_name = graphene.String()
        last_name = graphene.String()

    @login_required
    def mutate(self, info, **kwargs):
        user = info.context.user

        if kwargs.get("email") and user.email != kwargs.get("email"):
            email = kwargs["email"]
            # Check for unique constraint
            if get_user_model().objects.filter(email=email).exists():
                errors = [f"User with email {email} already exists"]
                return UpdateUser(success=False, errors=errors)

            try:
                validate_email(email)
                user.email = email
            except ValidationError as e:
                errors = get_error_messages(e)
                return UpdateUser(success=False, errors=errors)

        for field in ["first_name", "last_name"]:
            if kwargs.get(field):
                setattr(user, field, kwargs.get(field))

        try:
            user.save()
            return UpdateUser(success=True)
        except DjangoDBError as e:
            errors = get_error_messages(e)
            return UpdateUser(success=False, errors=errors)


class UpdatePassword(GenericResultMutation):
    class Arguments:
        old = graphene.String(required=True)
        new = graphene.String(required=True)

    @login_required
    def mutate(self, info, old, new):
        user = info.context.user
        encoded = user.password
        if check_password(old, encoded):
            user.set_password(new)
            user.save()
            return UpdatePassword(success=True)
        else:
            errors = ["Old password is incorrect"]
            return UpdatePassword(success=False, errors=errors)


# class GetTokenForResetPassword(graphene.Mutation):
#     success = graphene.Boolean()
#     errors = graphene.List(graphene.String)
#     token = graphene.String()
#
#     class Arguments:
#         username = graphene.String(required=True)
#
#     def mutate(self, info, username):
#         if get_user_model().objects.filter(username=username).exists():
#             # Encode with expiry 10 minutes after creation
#             encoded = jwt_encode(
#                 {
#                     "username": username,
#                     "exp": timezone.now() + timedelta(seconds=600),
#                 }
#             )
#             return GetTokenForResetPassword(success=True, token=encoded)
#
#         return GetTokenForResetPassword(
#             success=False, errors=["Invalid username"]
#         )


class ResetForgottenPassword(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    class Arguments:
        token = graphene.String(required=True)
        password = graphene.String(required=True)

    def mutate(self, info, token, password):
        try:
            decoded = jwt_decode(token)
        except InvalidTokenError:
            return ResetForgottenPassword(
                success=False, errors=["Invalid Token"]
            )

        username, exp = decoded["username"], decoded["exp"]

        if timezone.now().timestamp() > exp:
            return ResetForgottenPassword(
                success=False, errors=["Token expired"]
            )

        get_user = get_model_object(get_user_model(), username=username)

        if get_user.success:
            user = get_user.object
            user.set_password(password)
            user.save()
            return ResetForgottenPassword(success=True)
        else:
            return ResetForgottenPassword(
                success=get_user.success, errors=get_user.errors
            )


class DeleteUser(graphene.Mutation):
    """Mutation to delete a user"""

    @login_required
    def mutate(self, info, **kwargs):
        user = info.context.user

        delete_user_util(user)
        return DeleteUser(success=True)


class Mutation(object):
    verify_token = graphql_jwt.Verify.Field()
    refresh_token = graphql_jwt.Refresh.Field()
    register = Register.Field()
    login = Login.Field()
    logout = Logout.Field()
    update_user = UpdateUser.Field()
    delete_user = DeleteUser.Field()
    update_password = UpdatePassword.Field()
    is_username_valid = IsUsernameValid.Field()
    is_email_valid = IsEmailValid.Field()
    reset_forgotten_password = ResetForgottenPassword.Field()
    # get_token_for_reset_password = GetTokenForResetPassword.Field()
