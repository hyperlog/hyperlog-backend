import logging

import graphene
import graphql_jwt
from graphql import GraphQLError
from graphene_django import DjangoObjectType
from graphql_jwt import signals as jwt_signals
from graphql_jwt.decorators import login_required
from graphql_jwt.shortcuts import get_token

from django.contrib.auth import get_user_model, logout
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.utils import Error as DjangoDBError

from apps.base.schema import GenericResultMutation
from apps.base.utils import get_error_messages
from apps.users.models import User
from apps.users.utils import (
    create_user as create_user_util,
    delete_user as delete_user_util,
    generate_random_username,
    get_reset_password_link,
    github_get_gh_id,
    github_get_primary_email,
    github_get_user_data,
    github_trade_code_for_token,
    send_reset_password_email,
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
            "new_user",
            "login_types",
            "tagline",
            # From relations
            "profiles",
            "notifications",
            "widget",
            "stack_overflow",
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


class SendResetPasswordMail(GenericResultMutation):
    class Arguments:
        username = graphene.String(required=True)

    def mutate(self, info, username):
        UserModel = get_user_model()

        try:
            user = UserModel.objects.get(username=username)
        except UserModel.DoesNotExist:
            return SendResetPasswordMail(
                success=False, errors=["Invalid username"]
            )

        send_reset_password_email(user)
        return SendResetPasswordMail(success=True)


class DeleteUser(GenericResultMutation):
    """Mutation to delete a user"""

    @login_required
    def mutate(self, info, **kwargs):
        user = info.context.user

        delete_user_util(user)
        return DeleteUser(success=True)


class LoginWithGithub(GenericResultMutation):
    """Mutation to login user with GitHub OAuth"""

    token = graphene.String()
    user = graphene.Field(UserType)

    class Arguments:
        code = graphene.String(required=True)

    def mutate(self, info, code):
        UserModel = get_user_model()

        gh_token = github_trade_code_for_token(code)
        if gh_token:
            # Get user details
            gh_user_data = github_get_user_data(gh_token)
            if gh_user_data is None:
                return LoginWithGithub(
                    success=False, errors=["Couldn't connect with GitHub"]
                )

            gh_id, gh_login, name = (
                gh_user_data["databaseId"],
                gh_user_data["login"],
                gh_user_data["name"],
            )

            # Check if user already exists
            try:
                user = UserModel.objects.get(login_types__github__id=gh_id)
            except UserModel.DoesNotExist:
                email = github_get_primary_email(gh_token)
                if email is None:
                    return LoginWithGithub(
                        success=False, errors=["Something went wrong"]
                    )

                username = generate_random_username()

                # Try to create a new User
                if name:
                    name_split = name.split(maxsplit=1)
                    if len(name_split) == 2:
                        first_name, last_name = name_split
                    else:
                        first_name, last_name = name_split[0], ""
                else:
                    first_name, last_name = gh_login, ""

                user_create = create_user_util(
                    username=username,
                    email=email,
                    password=None,
                    first_name=first_name,
                    last_name=last_name,
                    new_user=True,
                    login_types={"github": {"id": gh_id}},
                )
                if not user_create.success:
                    return LoginWithGithub(
                        success=False, errors=user_create.errors
                    )

                user = user_create.object

            # Get the token and send a token_issued signal
            jwt_token = get_token(user)
            jwt_signals.token_issued.send(
                sender=self.__class__, request=info.context, user=user
            )

            return LoginWithGithub(success=True, token=jwt_token, user=user)
        else:
            return LoginWithGithub(
                success=False, errors=["Couldn't connect with GitHub"]
            )


class ChangeUsername(GenericResultMutation):
    """
    Mutation to change username for users who were given an random username
    """

    class Arguments:
        new = graphene.String(required=True)

    @login_required
    def mutate(self, info, new):
        user = info.context.user

        if user.new_user is True:
            user.username = new
            user.new_user = False

            try:
                user.full_clean()
            except ValidationError as e:
                return ChangeUsername(
                    success=False, errors=get_error_messages(e)
                )

            user.save()
            return ChangeUsername(success=True)

        else:
            return ChangeUsername(
                success=False,
                errors=[
                    "Oops, you cannot change your username. Consider contacting the support team."  # noqa: E501
                ],
            )


class AddGithubAuth(GenericResultMutation):
    """
    Mutation to associate an existing Hyperlog account with a GitHub Account
    for authentication
    """

    class Arguments:
        code = graphene.String(required=True)

    @login_required
    def mutate(self, info, code):
        user = info.context.user

        if "github" in user.login_types.keys():
            return LoginWithGithub(
                success=False,
                errors=["You've already added a GitHub account!"],
            )
        else:
            gh_token = github_trade_code_for_token(code)

            if gh_token:
                gh_id = github_get_gh_id(gh_token)

                # Check if the GitHub account is already added to some user
                if (
                    get_user_model()
                    .objects.filter(login_types__github__id=gh_id)
                    .exists()
                ):
                    return AddGithubAuth(
                        success=False,
                        errors=[
                            "This GitHub account is already added by a user."
                        ],
                    )
                else:
                    user.login_types["github"] = {"id": gh_id}
                    try:
                        user.full_clean()
                    except ValidationError as e:
                        return AddGithubAuth(
                            success=False, errors=get_error_messages(e)
                        )

                    user.save()
                    return AddGithubAuth(success=True)
            else:
                logger.error(f"Unable to fetch GitHub token for code '{code}'")
                return AddGithubAuth(
                    success=False, errors=["Something went wrong."]
                )


class GetLinkToCreatePassword(GenericResultMutation):
    url = graphene.String()

    @login_required
    def mutate(self, info, **kwargs):
        user = info.context.user

        if "password" in user.login_types:
            return GetLinkToCreatePassword(
                success=False, errors=["You already have a password!"]
            )

        reset_url = get_reset_password_link(user, "addNewAuth")
        return GetLinkToCreatePassword(success=True, url=reset_url)


class SetTagline(graphene.Mutation):
    success = graphene.Boolean(required=True)

    class Arguments:
        tagline = graphene.String(required=True)

    @login_required
    def mutate(self, info, tagline):
        user = info.context.user
        user.tagline = tagline

        try:
            user.full_clean()
        except ValidationError as e:
            raise GraphQLError(get_error_messages(e)[0])

        user.save()
        return SetTagline(success=True)


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
    send_reset_password_mail = SendResetPasswordMail.Field()
    login_with_github = LoginWithGithub.Field()
    change_username = ChangeUsername.Field()
    add_github_auth = AddGithubAuth.Field()
    get_link_to_create_password = GetLinkToCreatePassword.Field()
    set_tagline = SetTagline.Field()
