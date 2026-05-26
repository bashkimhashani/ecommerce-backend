import json

from django_redis import get_redis_connection
from redis.exceptions import RedisError

from .models import Conversation, ConversationMessage


class ChatHistoryStore:
    ttl_seconds = 86400
    max_entries = 20

    def get_history(self, session_id):
        redis_history = self.get_redis_history(session_id)
        if redis_history:
            return redis_history
        return self.get_db_history(session_id)

    def append_turn(self, session_id, tenant, user_message, assistant_message):
        entries = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message},
        ]
        self.append_redis_entries(session_id, entries)
        self.append_db_entries(session_id, tenant, entries)

    def get_redis_history(self, session_id):
        try:
            redis = get_redis_connection("default")
            raw_entries = redis.lrange(self.history_key(session_id), 0, -1)
        except RedisError:
            return []

        history = []
        for raw_entry in raw_entries:
            if isinstance(raw_entry, bytes):
                raw_entry = raw_entry.decode("utf-8")
            try:
                history.append(json.loads(raw_entry))
            except json.JSONDecodeError:
                continue
        return history

    def append_redis_entries(self, session_id, entries):
        try:
            redis = get_redis_connection("default")
            key = self.history_key(session_id)
            if entries:
                redis.rpush(key, *[json.dumps(entry) for entry in entries])
            redis.ltrim(key, -self.max_entries, -1)
            redis.expire(key, self.ttl_seconds)
        except RedisError:
            return

    def get_db_history(self, session_id):
        conversation = (
            Conversation.all_objects.filter(session_id=session_id)
            .order_by("-updated_at")
            .first()
        )
        if conversation is None:
            return []

        messages = conversation.messages.order_by("-created_at")[: self.max_entries]
        return [
            {"role": message.role, "content": message.content}
            for message in reversed(messages)
        ]

    def append_db_entries(self, session_id, tenant, entries):
        conversation, _ = Conversation.all_objects.get_or_create(
            session_id=session_id,
            defaults={"tenant": tenant},
        )
        if conversation.tenant_id is None and tenant is not None:
            conversation.tenant = tenant
            conversation.save(update_fields=["tenant", "updated_at"])

        for entry in entries:
            ConversationMessage.all_objects.create(
                tenant=conversation.tenant,
                conversation=conversation,
                role=entry["role"],
                content=entry["content"],
            )
        conversation.save(update_fields=["updated_at"])

    def history_key(self, session_id):
        return f"chat:{session_id}:history"
