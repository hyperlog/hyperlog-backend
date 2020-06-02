import logging

import graphene
import graphql_jwt
from graphene_django import DjangoObjectType
from graphql_jwt.decorators import login_required

from django.contrib.auth import get_user_model, logout
from django.contrib.auth.hashers import check_password
from django.db.utils import Error as DjangoDBError

from apps.users.models import User
from apps.users.utils import delete_user as delete_user_util

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
            "profiles",
            "notifications",
        ]


class Query(graphene.ObjectType):
    user = graphene.Field(UserType, id=graphene.Int(required=True))
    users = graphene.List(UserType)
    this_user = graphene.Field(UserType)

    @staticmethod
    def resolve_user(cls, info, **kwargs):
        return User.objects.get(id=kwargs.get("id"))

    @staticmethod
    def resolve_users(cls, info, **kwargs):
        return User.objects.all()

    @staticmethod
    @login_required
    def resolve_this_user(cls, info, **kwargs):
        if info.context.user.is_authenticated:
            return info.context.user


class Register(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    class Arguments:
        email = graphene.String(required=True)
        username = graphene.String(required=True)
        password = graphene.String(required=True)
        first_name = graphene.String(required=True)
        last_name = graphene.String(required=True)

    def mutate(self, info, email, username, password, first_name, last_name):
        if User.objects.filter(email__iexact=email).exists():
            errors = ["emailAlreadyExists"]
            return Register(success=False, errors=errors)

        if User.objects.filter(username__iexact=username).exists():
            errors = ["usernameAlreadyExists"]
            return Register(success=False, errors=errors)

        # create user
        user = User.objects.create(
            username=username,
            email=email,
            last_name=last_name,
            first_name=first_name,
        )
        user.set_password(password)
        user.save()
        return Register(success=True)


class Logout(graphene.Mutation):
    """ Mutation to logout a user """

    success = graphene.Boolean()

    def mutate(self, info):
        logout(info.context)
        return Logout(success=True)


class UpdateUser(graphene.Mutation):
    """Mutation to update user's profile details"""

    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    class Arguments:
        password = graphene.String()
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

            user.email = email

        for field in ["first_name", "last_name"]:
            if kwargs.get(field):
                setattr(user, field, kwargs.get(field))

        if kwargs.get("password"):
            user.set_password(kwargs.get("password"))

        try:
            user.save()
            return UpdateUser(success=True)
        except DjangoDBError as err:
            return UpdateUser(success=False, errors=[str(err)])
        except Exception:
            # Hide the error log from user here as it could be a bug
            logger.error("Error in UpdateUser mutation", exc_info=True)
            return UpdateUser(success=False, errors=["server error"])


class UpdatePassword(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    class Arguments:
        old = graphene.String(required=True)
        new = graphene.String(required=True)

    @login_required
    def mutate(self, info, old, new):
        user = info.context.user
        encoded = user.password
        if check_password(old, encoded):
            try:
                user.set_password(new)
                return UpdatePassword(success=True)
            except Exception:
                logger.error("Error in UpdatePassword mutation", exc_info=True)
                return UpdatePassword(success=False, errors=["server error"])
        else:
            errors = ["Old password is incorrect"]
            return UpdatePassword(success=False, errors=errors)


class DeleteUser(graphene.Mutation):
    """Mutation to delete a user"""

    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @login_required
    def mutate(self, info, **kwargs):
        user = info.context.user

        try:
            delete_user_util(user)
            return DeleteUser(success=True)
        except Exception:
            logger.error("Error in DeleteUser mutation", exc_info=True)
            return DeleteUser(success=False, errors=["server error"])


class Mutation(object):
    login = graphql_jwt.ObtainJSONWebToken.Field()
    verify_token = graphql_jwt.Verify.Field()
    refresh_token = graphql_jwt.Refresh.Field()
    register = Register.Field()
    logout = Logout.Field()
    update_user = UpdateUser.Field()
    delete_user = DeleteUser.Field()
    update_password = UpdatePassword.Field()
