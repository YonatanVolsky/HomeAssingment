"""The prompt loop. Reading, writing and the connection are passed in, so it can be tested."""

from collections.abc import Callable
from typing import Any, Protocol

from app.client.commands import Help, Invalid, Quit, Send, ToggleJson, health, parse
from app.client.connection import ConnectionFailed
from app.client.render import render

PROMPT = 'collector> '
HELP = """\
<subreddit>           newest posts: stored if recent, otherwise collected now (:auto)
:live <subreddit>     always collect from Reddit now
:stored <subreddit>   only what is stored; never calls Reddit
:health               the collector's status and mode
:json                 switch raw JSON output on or off
:help                 this list
:quit                 leave (or Ctrl+D)
Ctrl+C while waiting cancels that request."""


class Connection(Protocol):
    host: str
    port: int

    def send(self, message: dict[str, Any]) -> dict[str, Any]: ...


class Repl:
    def __init__(
        self,
        connection: Connection,
        read: Callable[[str], str],
        write: Callable[[str], None],
        width: Callable[[], int | None] = lambda: None,
    ) -> None:
        """`width` gives the terminal width at each reply (None: never cut lines)."""
        self._connection = connection
        self._read = read
        self._write = write
        self._width = width
        self._as_json = False

    def run(self) -> None:
        self._greet()
        while True:
            try:
                line = self._read(PROMPT)
            except (EOFError, KeyboardInterrupt):
                self._write('')
                return
            command = parse(line)
            if isinstance(command, Quit):
                return
            self._do(command)

    def _greet(self) -> None:
        where = f'{self._connection.host}:{self._connection.port}'
        try:
            reply = self._connection.send(health().message)
        except ConnectionFailed as error:
            self._write(f'{error}. Start it with "npm run dev:inner"; each command tries again.')
        else:
            mode = reply['result']['collectorMode'] if reply['ok'] else 'unknown'
            self._write(f'Connected to the collector at {where} ({mode} mode).')
        self._write('Type a subreddit, or :help for commands.')

    def _do(self, command: Send | ToggleJson | Help | Invalid | None) -> None:
        if isinstance(command, Invalid):
            self._write(command.reason)
        elif isinstance(command, Help):
            self._write(HELP)
        elif isinstance(command, ToggleJson):
            self._as_json = not self._as_json
            self._write(f'JSON output {"on" if self._as_json else "off"}.')
        elif isinstance(command, Send):
            self._send(command.message)

    def _send(self, message: dict[str, Any]) -> None:
        try:
            reply = self._connection.send(message)
        except ConnectionFailed as error:
            self._write(str(error))
        except KeyboardInterrupt:
            self._write('Cancelled.')
        else:
            self._write(
                render(message['resource'], reply, as_json=self._as_json, width=self._width())
            )
