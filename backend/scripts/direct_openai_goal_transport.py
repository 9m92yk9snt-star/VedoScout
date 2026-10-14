"""Isolated single-call transport for the original goal review, no Emergent SDK."""
import asyncio
import json
import urllib.error
import urllib.request


class DirectGoalChat:
    def __init__(self, *, api_key, session_id, system_message):
        self.api_key = api_key
        self.system_message = system_message
        self.model = None
        self.timeout = 55.0
        self.sent = False

    def with_model(self, provider, model):
        if provider != 'openai':
            raise ValueError('DIRECT_TEST_REQUIRES_OPENAI_PROVIDER')
        self.model = model
        return self

    def with_params(self, **kwargs):
        self.timeout = min(55.0, float(kwargs.get('timeout', 55)))
        return self

    async def send_message(self, message):
        if self.sent:
            raise RuntimeError('DIRECT_TEST_SECOND_CALL_BLOCKED')
        self.sent = True
        return await asyncio.to_thread(self._send, message)

    def _send(self, message):
        content = [{'type': 'text', 'text': message.text}]
        for image in message.file_contents:
            content.append({'type': 'image_url', 'image_url': {
                'url': 'data:image/jpeg;base64,' + image.image_base64, 'detail': 'high'}})
        payload = {'model': self.model, 'messages': [
            {'role': 'system', 'content': self.system_message},
            {'role': 'user', 'content': content}],
            'response_format': {'type': 'json_object'}, 'max_completion_tokens': 16384,
            'store': False}
        request = urllib.request.Request('https://api.openai.com/v1/chat/completions',
            data=json.dumps(payload).encode(), method='POST', headers={
                'Authorization': 'Bearer ' + self.api_key, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read(2_000_000))
        except urllib.error.HTTPError as exc:
            # Never log request headers, API response bodies, or credentials.
            status = exc.code
            exc.close()
            raise RuntimeError('DIRECT_OPENAI_HTTP_' + str(status)) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError('DIRECT_OPENAI_CONNECTION_FAILED') from None
        choices = data.get('choices')
        if not isinstance(choices, list) or len(choices) != 1:
            raise RuntimeError('DIRECT_OPENAI_INVALID_RESPONSE')
        row = choices[0]
        if row.get('finish_reason') != 'stop':
            raise RuntimeError('DIRECT_OPENAI_INCOMPLETE_RESPONSE')
        text = (row.get('message') or {}).get('content')
        if not isinstance(text, str) or not text:
            raise RuntimeError('DIRECT_OPENAI_EMPTY_RESPONSE')
        return text


class Payload:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
