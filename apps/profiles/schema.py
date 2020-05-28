import graphene
from graphene_django import DjangoObjectType
from graphql_jwt.decorators import staff_member_required, login_required

from django.contrib.auth import get_user_model

from apps.profiles.models import (
    BaseProfileModel,
    EmailAddress,
    GithubProfile,
    Notification,
)
from apps.profiles.utils import get_model_object


class ProfileType(DjangoObjectType):
    class Meta:
        model = BaseProfileModel
        exclude = ("_provider", "emails")

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


class CreateGithubProfile(graphene.Mutation):
    profile = graphene.Field(ProfileType)

    class Arguments:
        username = graphene.String(required=True)
        access_token = graphene.String(required=True)
        emails = graphene.List(graphene.String, required=True)

    @login_required
    def mutate(self, info, username, access_token, emails):
        user = info.context.user
        new_profile = GithubProfile.objects.create(
            username=username, access_token=access_token, user=user
        )

        for email in emails:
            EmailAddress.objects.create(email=email, profile=new_profile)

        return CreateGithubProfile(profile=new_profile)


class CreateNotification(graphene.Mutation):
    success = graphene.String()
    errors = graphene.List(graphene.String)
    notification = graphene.Field(NotificationType)

    class Arguments:
        priority = graphene.String(required=True)
        heading = graphene.String(required=True)
        sub = graphene.String(required=True)
        read = graphene.Boolean()
        user_id = graphene.Int(required=True)

    def mutate(self, info, priority, heading, sub, read, user_id):
        try:
            user = get_model_object(get_user_model(), id=user_id)
            notification = Notification.objects.create(
                user=user,
                priority=priority,
                read=read,
                heading=heading,
                sub=sub,
            )
            return CreateNotification(success=True, notification=notification)

        except Exception as e:
            errors = [str(e)]
            return CreateNotification(success=False, errors=errors)


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
            errors = [str(e)]
            return MarkNotificationAsRead(success=False, errors=errors)

        return MarkNotificationAsRead(success=True)


class Mutation(graphene.ObjectType):
    create_github_profile = CreateGithubProfile.Field()
    mark_notification_as_read = MarkNotificationAsRead.Field()
