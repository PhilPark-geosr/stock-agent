"""Send a fixed test message independently of analysis and alert evaluation."""

from app.interfaces.notifications import NotificationSender


TEST_MESSAGE = '[Stock Agent] 테스트 알림입니다. 카카오 알림 연결을 확인해 주세요.'


class NotificationTestConnectionRequired(RuntimeError):
    pass


class NotificationTestService:
    def __init__(self, connections, sender: NotificationSender):
        self.connections = connections
        self.sender = sender

    def send(self, owner_id: str) -> None:
        connection = self.connections.get_active(owner_id=owner_id, channel='kakao')
        if connection is None:
            raise NotificationTestConnectionRequired()
        self.sender.send(connection=connection, message=TEST_MESSAGE)
