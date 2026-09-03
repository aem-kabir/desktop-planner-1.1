"""
single_instance.py
Гарантирует, что запущен только один экземпляр приложения.
Повторный запуск .exe отправляет сигнал уже запущенному процессу
(через QLocalSocket) развернуть окно, а сам новый процесс завершается.
"""
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from config import APP_NAME

SERVER_NAME = f"{APP_NAME}_SingleInstanceLock"
SHOW_MESSAGE = b"SHOW"


class SingleInstanceGuard(QObject):
    show_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._server = None

    def try_acquire(self) -> bool:
        """
        Возвращает True, если это первый (главный) экземпляр — тогда поднимаем
        локальный сервер и слушаем сообщения от повторных запусков.
        Возвращает False, если экземпляр уже запущен — тогда сигналим ему
        и вызывающий код должен завершить процесс.
        """
        socket = QLocalSocket()
        socket.connectToServer(SERVER_NAME)
        if socket.waitForConnected(200):
            # Уже есть работающий экземпляр — просим его показаться
            socket.write(SHOW_MESSAGE)
            socket.waitForBytesWritten(200)
            socket.disconnectFromServer()
            return False

        # Нет работающего экземпляра — становимся им.
        # На случай "призрачного" сервера от аварийно завершённого процесса.
        QLocalServer.removeServer(SERVER_NAME)
        self._server = QLocalServer()
        self._server.newConnection.connect(self._on_new_connection)
        self._server.listen(SERVER_NAME)
        return True

    def _on_new_connection(self):
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.readyRead.connect(lambda: self._on_ready_read(conn))

    def _on_ready_read(self, conn):
        data = conn.readAll()
        if bytes(data) == SHOW_MESSAGE:
            self.show_requested.emit()
        conn.disconnectFromServer()
