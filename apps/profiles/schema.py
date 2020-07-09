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
from apps.base.utils import (
    create_model_object,
    get_error_messages,
    get_model_object,
)
from apps.profiles.utils import (
    dynamodb_convert_boto_dict_to_python_dict,
    dynamodb_get_profile,
    push_profile_analysis_to_sqs_queue,
)

logger = logging.getLogger(__name__)

MAX_PROFILE_ANALYSES_PER_USER = 5


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
    profiles = graphene.List(ProfileType, provider=graphene.String())
    profile = graphene.Field(ProfileType, id=graphene.Int(required=True))
    profile_emails = graphene.List(EmailAddressType)

    notifications = graphene.List(
        NotificationType, conditions=graphene.JSONString()
    )
    notification = graphene.Field(
        NotificationType, id=graphene.Int(required=True)
    )
    notifications_count = graphene.Int(conditions=graphene.JSONString())

    profile_analyses_used = graphene.Int(
        description="The number of profile analyses used by the user"
    )

    def resolve_notifications(self, info, **kwargs):
        conditions = kwargs.get("conditions")
        if conditions:
            return Notification.objects.filter(**conditions)
        else:
            return Notification.objects.all()

    def resolve_notification(self, info, **kwargs):
        return Notification.objects.get(id=kwargs.get("id"))

    def resolve_notifications_count(self, info, **kwargs):
        conditions = kwargs.get("conditions")
        if conditions:
            return Notification.objects.filter(**conditions).count()
        else:
            return Notification.objects.count()

    def resolve_profiles(self, info, **kwargs):
        """
        Returns all profiles with given provider or simply all profiles if it
        is not mentioned
        """
        if kwargs.get("provider"):
            return BaseProfileModel.objects.filter(
                _provider=kwargs.get("provider")
            )
        return BaseProfileModel.objects.all()

    @staff_member_required
    def resolve_profile(self, info, **kwargs):
        return BaseProfileModel.objects.get(id=kwargs.get("id"))

    def resolve_profile_emails(self, info, **kwargs):
        return EmailAddress.objects.all()

    @login_required
    def resolve_profile_analyses_used(self, info, **kwargs):
        return len(info.context.user.profile_analyses.all())


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

        try:
            profile.delete()
            return DeleteGithubProfile(success=True)
        except Exception:
            logger.error("Error in DeleteGithubProfile mutation")
            return DeleteGithubProfile(success=False, errors=["server error"])


class CreateNotification(graphene.Mutation):
    success = graphene.String()
    errors = graphene.List(graphene.String)
    notification = graphene.Field(NotificationType)

    class Arguments:
        user_id = graphene.Int(required=True)
        heading = graphene.String(required=True)
        sub = graphene.String(required=True)
        read = graphene.Boolean()
        priority = graphene.Int()

    def mutate(self, info, user_id, **kwargs):
        try:
            # try to get the user
            user_result = get_model_object(get_user_model(), id=user_id)

            if user_result.success:
                user = user_result.object
            else:
                # User could not be found
                return CreateNotification(
                    success=False, errors=user_result.errors
                )

            # validate and create notification object
            result = create_model_object(Notification, user=user, **kwargs)
            return CreateNotification(
                success=result.success,
                notification=result.object,
                errors=result.errors if result.success is False else None,
            )
        except Exception as e:
            logger.exception(e)
            return CreateNotification(success=False, errors=["server error"])


class MarkNotificationAsRead(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    class Arguments:
        id = graphene.Int(required=True)

    def mutate(self, info, id):
        try:
            notification = get_model_object(Notification, id=id)
            notification.read = True
            notification.save()
        except Exception as e:
            errors = get_error_messages(e)
            return MarkNotificationAsRead(success=False, errors=errors)

        return MarkNotificationAsRead(success=True)


class AnalyseProfile(graphene.Mutation):
    """Mutation to run profile analysis for user"""

    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @login_required
    def mutate(self, info):
        user = info.context.user

        # Get the github token if a github account is associated with user
        if hasattr(user, "profiles"):
            try:
                gh_profile = user.profiles.get(_provider="github")
            except BaseProfileModel.DoesNotExist:
                error = "No github account is associated with the user"
                return AnalyseProfile(success=False, errors=[error])
        else:
            error = "No github account is associated with the user"
            return AnalyseProfile(success=False, errors=[error])

        github_token = gh_profile.access_token

        # Get data from DynamoDB
        user_profile = dynamodb_convert_boto_dict_to_python_dict(
            dynamodb_get_profile(user.id)
        )

        # Check if user has finished their quota
        if user_profile["turn"] >= MAX_PROFILE_ANALYSES_PER_USER:
            error = (
                "You've completed the limit of %i runs of profile analysis"
                % MAX_PROFILE_ANALYSES_PER_USER
            )
            return AnalyseProfile(success=False, errors=[error])

        # Check if an analyse task is already running
        status = user_profile["status"]
        if status == "in_progress":
            error = "You already have an analysis running. Please wait"
            return AnalyseProfile(success=False, errors=[error])

        # Push user_id and github_token to SQS queue
        try:
            response = push_profile_analysis_to_sqs_queue(
                user.id, github_token
            )
            logger.info(
                "Message ID %s for profile analysis pushed to SQS queue"
                % response["MessageId"]
            )
        except botocore.exceptions.ClientError:
            logger.error("AWS SQS Error", exc_info=True)
            return AnalyseProfile(success=False, errors=["server error"])

        # Save the analysis log to database
        create_analysis = create_model_object(ProfileAnalysis, user=user)
        if not create_analysis.success:
            logger.critical(
                "Unable to create ProfileAnalysis object, errors:\n%(errors)s"
                % {"errors": "\n".join(create_analysis.errors)}
            )
            # Sending success=True message because the process was queued
            return AnalyseProfile(success=True)

        # Successfully completed
        return AnalyseProfile(success=True)


class Mutation(graphene.ObjectType):
    delete_github_profile = DeleteGithubProfile.Field()
    create_notification = CreateNotification.Field()
    mark_notification_as_read = MarkNotificationAsRead.Field()
    analyse_profile = AnalyseProfile.Field()
