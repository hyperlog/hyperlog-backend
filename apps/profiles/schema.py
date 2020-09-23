import logging

import botocore
import graphene
import requests
from graphql import GraphQLError
from graphene_django import DjangoObjectType
from graphql_jwt.decorators import staff_member_required, login_required

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.base.github import (
    github_trade_code_for_token,
    github_get_user_data,
    get_user_emails as github_get_user_emails,
)
from apps.base.schema import GenericResultMutation
from apps.base.utils import (
    create_model_object,
    get_error_messages,
    get_model_object,
)
from apps.profiles.models import (
    BaseProfileModel,
    EmailAddress,
    GithubProfile,
    Notification,
    ProfileAnalysis,
    StackOverflowProfile,
)
from apps.profiles.utils import (
    create_profile_object,
    dynamodb_add_selected_repos_to_profile_analysis_table,
    dynamodb_convert_boto_dict_to_python_dict,
    dynamodb_get_profile,
    stack_overflow_get_user_data,
    trigger_analysis,
)

GITHUB_CLIENT_ID = settings.GITHUB_CLIENT_ID
GITHUB_CLIENT_SECRET = settings.GITHUB_CLIENT_SECRET

STACK_OVERFLOW_TOKEN_URL = "https://stackoverflow.com/oauth/access_token/json"
STACK_OVERFLOW_CLIENT_ID = settings.STACK_OVERFLOW_CLIENT_ID
STACK_OVERFLOW_CLIENT_SECRET = settings.STACK_OVERFLOW_CLIENT_SECRET
STACK_OVERFLOW_REDIRECT_URI = settings.STACK_OVERFLOW_REDIRECT_URI


logger = logging.getLogger(__name__)


class ProfileType(DjangoObjectType):
    class Meta:
        model = BaseProfileModel
        exclude = ("_provider",)

    provider = graphene.String()
    emails = graphene.List(graphene.String)

    def resolve_provider(self, info):
        return self._provider

    def resolve_emails(self, info):
        return [each.email for each in self.emails.all()]


class EmailAddressType(DjangoObjectType):
    class Meta:
        model = EmailAddress


class NotificationType(DjangoObjectType):
    class Meta:
        model = Notification


class StackOverflowProfileType(DjangoObjectType):
    class Meta:
        model = StackOverflowProfile


class Query(graphene.ObjectType):
    profile = graphene.Field(ProfileType, id=graphene.Int(required=True))

    notification = graphene.Field(
        NotificationType, id=graphene.Int(required=True)
    )
    notifications_count = graphene.Int(conditions=graphene.JSONString())

    profile_analyses_used = graphene.Int(
        description="The number of profile analyses used by the user"
    )

    def resolve_notification(self, info, **kwargs):
        return Notification.objects.get(id=kwargs.get("id"))

    def resolve_notifications_count(self, info, **kwargs):
        conditions = kwargs.get("conditions")
        if conditions:
            return Notification.objects.filter(**conditions).count()
        else:
            return Notification.objects.count()

    @staff_member_required
    def resolve_profile(self, info, **kwargs):
        return BaseProfileModel.objects.get(id=kwargs.get("id"))

    @login_required
    def resolve_profile_analyses_used(self, info, **kwargs):
        user_profile = dynamodb_convert_boto_dict_to_python_dict(
            dynamodb_get_profile(info.context.user.id)
        )
        return user_profile["turn"]


class DeleteGithubProfile(GenericResultMutation):
    @login_required
    def mutate(self, info, **kwargs):
        user = info.context.user

        try:
            profile = user.profiles.get(_provider="github")
        except BaseProfileModel.DoesNotExist:
            errors = ["GitHub account is not associated."]
            return DeleteGithubProfile(success=False, errors=errors)

        profile.delete()
        return DeleteGithubProfile(success=True)


class CreateNotification(GenericResultMutation):
    notification = graphene.Field(NotificationType)

    class Arguments:
        user_id = graphene.UUID(required=True)
        heading = graphene.String(required=True)
        sub = graphene.String(required=True)
        read = graphene.Boolean()
        priority = graphene.Int()

    def mutate(self, info, user_id, **kwargs):
        # try to get the user
        user_result = get_model_object(get_user_model(), id=user_id)

        if user_result.success:
            user = user_result.object
        else:
            # User could not be found
            return CreateNotification(success=False, errors=user_result.errors)

        # validate and create notification object
        result = create_model_object(Notification, user=user, **kwargs)
        return CreateNotification(
            success=result.success,
            notification=result.object,
            errors=result.errors if result.success is False else None,
        )


class MarkNotificationAsRead(GenericResultMutation):
    class Arguments:
        id = graphene.Int(required=True)

    def mutate(self, info, id):
        get_notification = get_model_object(Notification, id=id)

        if get_notification.success:
            notification = get_notification.object
            notification.read = True
            notification.save()
            return MarkNotificationAsRead(success=True)
        else:
            return MarkNotificationAsRead(
                success=get_notification.success,
                errors=get_notification.errors,
            )


class SelectRepos(GenericResultMutation):
    """Mutation to select repos and trigger analysis"""

    class Arguments:
        repos = graphene.NonNull(
            graphene.List(graphene.NonNull(graphene.String))
        )

    @login_required
    def mutate(self, info, repos):
        user = info.context.user

        try:
            result = dynamodb_add_selected_repos_to_profile_analysis_table(
                user.id, repos
            )
            logger.info(
                f"Added selected repos to dynamodb for user: {user.id}, "
                f"repos: {repos}\nResponse: {result}"
            )
        except AssertionError as e:
            return SelectRepos(success=False, errors=get_error_messages(e))
        except botocore.exceptions.ClientError as e:
            if (
                e.response["Error"]["Code"]
                == "ConditionalCheckFailedException"
            ):
                logger.exception("Failed conditional check")
                return SelectRepos(success=False, errors=["Invalid request"])

            logger.exception("Botocore error")
            return SelectRepos(success=False, errors=["server error"])

        # Get the github token if a github account is associated with user
        if hasattr(user, "profiles"):
            try:
                gh_profile = user.profiles.get(_provider="github")
            except BaseProfileModel.DoesNotExist:
                error = "No github account is associated with the user"
                return SelectRepos(success=False, errors=[error])
        else:
            error = "No github account is associated with the user"
            return SelectRepos(success=False, errors=[error])

        github_token = gh_profile.access_token

        analysis_result = trigger_analysis(user, github_token)

        if analysis_result["success"]:
            # Save the analysis log to database
            save_analysis = create_model_object(ProfileAnalysis, user=user)
            if not save_analysis.success:
                logger.critical(
                    "Unable to save ProfileAnalysis to db, errors:\n%(errors)s"
                    % {"errors": "\n".join(save_analysis.errors)}
                )

        return SelectRepos(**analysis_result)


class ConnectGithub(GenericResultMutation):
    class Arguments:
        code = graphene.String(required=True)

    @login_required
    def mutate(self, info, code):
        user = info.context.user

        if user.profiles.filter(_provider="github").exists():
            raise GraphQLError("You have already connected a GitHub account!")

        # TODO: Edit trade_token function to check the scope of token
        gh_token = github_trade_code_for_token(
            code, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET
        )

        # Get user data
        if gh_token:
            gh_user_data = github_get_user_data(gh_token)

            # Unable to fetch user data
            if gh_user_data is None:
                raise GraphQLError("Couldn't connect with GitHub API")

            gh_id, gh_login = gh_user_data["databaseId"], gh_user_data["login"]

            # Try to create a GitHub Profile
            profile_creation = create_profile_object(
                GithubProfile,
                access_token=gh_token,
                username=gh_login,
                provider_uid=gh_id,
                user=user,
            )

            if profile_creation.success:
                profile = profile_creation.object
                emails = github_get_user_emails(gh_token)
                for email_dict in emails:
                    # TODO: Add primary and verified parameters
                    create_model_object(
                        EmailAddress,
                        email=email_dict.get("email"),
                        profile=profile,
                    )

                return ConnectGithub(success=True)
            else:
                raise GraphQLError("\n".join(profile_creation.errors))
        else:
            raise GraphQLError("Couldn't connect with GitHub")


class ConnectStackOverflow(GenericResultMutation):
    class Arguments:
        code = graphene.String(required=True)

    @login_required
    def mutate(self, info, code):
        user = info.context.user

        post_data = {
            "client_id": STACK_OVERFLOW_CLIENT_ID,
            "client_secret": STACK_OVERFLOW_CLIENT_SECRET,
            "code": code,
            "redirect_uri": STACK_OVERFLOW_REDIRECT_URI or "http://localhost",
        }

        oauth_response = requests.post(
            STACK_OVERFLOW_TOKEN_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data="&".join([f"{key}={val}" for key, val in post_data.items()]),
        )
        data = oauth_response.json()

        if (
            oauth_response.status_code != requests.codes.ok
            or "error_message" in data
        ):
            logger.error(
                "Failed while trying to fetch token from StackOverflow\n"
                f"Status Code: {oauth_response.status_code}\n"
                f"Response: {data}"
            )
            return ConnectStackOverflow(
                success=False,
                errors=["Something went wrong. Please try again"],
            )
        else:
            access_token = data["access_token"]

            user_data = stack_overflow_get_user_data(access_token)
            print(user_data)
            if user_data is None:
                return ConnectStackOverflow(
                    success=False,
                    errors=["Something went wrong. Please try again"],
                )

            stack_profile_creation = create_model_object(
                StackOverflowProfile, user=user, **user_data
            )
            print(f"id: {stack_profile_creation.object.id}")
            return ConnectStackOverflow(
                success=stack_profile_creation.success,
                errors=stack_profile_creation.errors,
            )


class Mutation(graphene.ObjectType):
    delete_github_profile = DeleteGithubProfile.Field()
    create_notification = CreateNotification.Field()
    mark_notification_as_read = MarkNotificationAsRead.Field()
    select_repos = SelectRepos.Field()
    connect_stackoverflow = ConnectStackOverflow.Field()
    connect_github = ConnectGithub.Field()
