import logging

import graphene
from graphql import GraphQLError
from graphql_jwt.decorators import login_required

from django.contrib.auth import get_user_model

from apps.base.telegram import telegram_bot_required
from apps.base.utils import create_model_object, get_model_object
from apps.messaging.models import TelegramMessage, TelegramUser
from apps.messaging.telegram import send_tg_message


logger = logging.getLogger(__name__)


class Query(graphene.ObjectType):
    pass


class RegisterTelegramUser(graphene.Mutation):
    created = graphene.Boolean(required=True)

    class Arguments:
        id = graphene.String(required=True)
        first_name = graphene.String(required=True)
        last_name = graphene.String(required=False, default_value="")

    @telegram_bot_required
    def mutate(self, info, id, first_name, last_name):
        tg_user, created = TelegramUser.objects.get_or_create(
            id=id, defaults={"first_name": first_name, "last_name": last_name}
        )
        return RegisterTelegramUser(created=created)


class MessageHyperlogUserFromTelegram(graphene.Mutation):
    message_id = graphene.Int(required=True)

    class Arguments:
        to = graphene.String(required=True)
        chat_id = graphene.String(required=True)
        msg_id = graphene.String(required=True)
        text = graphene.String(required=True)

    @telegram_bot_required
    def mutate(self, info, to, chat_id, msg_id, text):
        UserModel = get_user_model()
        tg_user = get_model_object(TelegramUser, id=chat_id)
        if tg_user.success:
            tg_user = tg_user.object
        else:
            logger.error(tg_user.errors)
            raise GraphQLError(
                "Something went wrong! Have you registered with Hyperlog's "
                "Telegram OAuth? You can do it from the 'Get in Touch' section"
                " on any webpage on the hyperlog.dev subdomain "
                "(e.g. https://kaustubh.hyperlog.dev/)"
            )

        hl_user = get_model_object(UserModel, username=to)
        if hl_user.success:
            hl_user = hl_user.object
        else:
            logger.error(hl_user.errors)
            raise GraphQLError(
                "I couldn't find the person you want to reach out to. "
                "Maybe they recently deleted their Hyperlog account."
            )

        msg_create = create_model_object(
            TelegramMessage,
            tg_message_id=msg_id,
            hl_user=hl_user,
            tg_user=tg_user,
            is_outgoing=False,
            text=text,
        )
        if msg_create.success:
            return MessageHyperlogUserFromTelegram(
                message_id=msg_create.object.id
            )
        else:
            raise GraphQLError(msg_create.errors)


class MessageTelegramUserFromHyperlog(graphene.Mutation):
    message_id = graphene.Int(required=True)

    class Arguments:
        tg_user_id = graphene.String(required=True)  # Chat id
        text = graphene.String(required=True)

    @login_required
    def mutate(self, info, tg_user_id, text):
        tg_user = get_model_object(TelegramUser, id=tg_user_id)
        if tg_user.success:
            tg_user = tg_user.object
        else:
            raise GraphQLError(tg_user.errors[0])

        hl_user = info.context.user
        resp = send_tg_message(hl_user, tg_user, text)
        return MessageTelegramUserFromHyperlog(message_id=resp.id)


class Mutation(graphene.ObjectType):
    register_telegram_user = RegisterTelegramUser.Field()
    message_hyperlog_user_from_telegram = (
        MessageHyperlogUserFromTelegram.Field()
    )
    message_telegram_user_from_hyperlog = (
        MessageTelegramUserFromHyperlog.Field()
    )
