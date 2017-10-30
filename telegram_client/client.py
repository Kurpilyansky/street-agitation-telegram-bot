import time
import re
import json
import socket
import subprocess


class TelegramClient:
    def __init__(self, hostname, port):
        self._socket = None
        self._process = None
        self._server_started = False
        self.hostname = hostname
        self.port = port

    class TryAgainError(Exception):
        pass

    def make_request(self, request):
        return self.make_complex_request(lambda make: make(request))

    def make_complex_request(self, request_func):
        for attempt in range(10):
            try:
                return request_func(self._try_make_request)
            except self.TryAgainError:
                pass
        raise AssertionError('Can not receive answer from TelegramClient')

    def close(self):
        self._stop_server()

    def _try_make_request(self, request):
        self._ensure_start()
        print(request)
        self._socket.send(str.encode(request + '\n'))
        self._socket.settimeout(2.0)
        try:
            response = self._socket.recv(2048)
        except socket.timeout:
            self._stop_server()
            raise self.TryAgainError()
        print(response)
        response = response.decode()
        match = re.match('ANSWER (\d+)\n(.*)', response)
        if bool(match):
            return json.loads(match.group(2))
        return None

    def _ensure_start(self):
        if not self._server_started:
            self._process = subprocess.Popen(['/home/eugene/navalny-dev/tg/bin/telegram-cli',
                                              '-W', '--json', '-P %d' % self.port],
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE)
            self._server_started = True
            time.sleep(1.0)
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self.hostname, self.port))

    def _stop_server(self):
        if self._server_started:
            self._socket.close()
            self._socket = None
            self._process.kill()
            self._process = None
            self._server_started = False

