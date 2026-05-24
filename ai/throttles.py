from rest_framework.throttling import UserRateThrottle


class ChatRateThrottle(UserRateThrottle):
    scope = 'chat_message'
    rate = '20/min'
