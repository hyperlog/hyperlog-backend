import graphene

from apps.base.telegram import telegram_bot_required


class MessageHyperlogUserFromTelegram(graphene.Mutation):
    message_id = graphene.Int(required=True)

    class Arguments:
        to = graphene.String(required=True)
        chat_id = graphene.String(required=True)
        text = graphene.String(required=True)

    @telegram_bot_required
    def mutate(self, info, to, chat_id, text):
        print(f"{chat_id} -> {to}: {text}")
        return MessageHyperlogUserFromTelegram(message_id=0)
