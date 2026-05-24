from django.urls import path

from .views import ChatHistoryView, ChatMessageView


urlpatterns = [
    path('message/', ChatMessageView.as_view(), name='chat-message'),
    path(
        'history/<str:session_id>/',
        ChatHistoryView.as_view(),
        name='chat-history',
    ),
]
