import logging

import botocore
import graphene
from graphene_django import DjangoObjectType
from graphql_jwt.decorators import staff_member_required, login_required

from django.contrib.auth import get_user_model

from apps.profiles.models import (
    BaseProfileModel,
    EmailAddress,
    Notification,
    ProfileAnalysis,
)
from apps.base.schema import GenericResultMutation
from apps.base.utils import (
    create_model_object,
    get_error_messages,
    get_model_object,
)
from apps.profiles.utils import (
    dynamodb_add_selected_repos_to_profile_analysis_table,
    dynamodb_convert_boto_dict_to_python_dict,
    dynamodb_get_profile,
    trigger_analysis,
)

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


class DeleteGithubProfile(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

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


class CreateNotification(graphene.Mutation):
    success = graphene.String()
    errors = graphene.List(graphene.String)
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


class MarkNotificationAsRead(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

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


class Mutation(graphene.ObjectType):
    delete_github_profile = DeleteGithubProfile.Field()
    create_notification = CreateNotification.Field()
    mark_notification_as_read = MarkNotificationAsRead.Field()
    select_repos = SelectRepos.Field()
