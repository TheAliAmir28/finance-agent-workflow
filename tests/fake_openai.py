"""Minimal scripted stand-in for the OpenAI chat-completions client."""

import json
from types import SimpleNamespace


def tool_call(call_id, name, **arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))


def assistant_turn(tool_calls=None, content=None):
    message = SimpleNamespace(role="assistant", content=content,
                              tool_calls=tool_calls or None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    """Returns scripted responses in order; records every request."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeClient ran out of scripted responses")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
