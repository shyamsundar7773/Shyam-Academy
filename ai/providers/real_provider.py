import json
import os
from urllib import error, request

from ai.gateway import AIProviderError


class RealProviderError(AIProviderError):
    """Classified error from the configured real AI provider."""


class RealProvider:
    """OpenAI-compatible provider adapter with secret-safe errors."""

    def __init__(self, api_key=None, model=None, base_url=None, timeout=30):
        self.api_key = api_key or os.getenv("SHYAM_ACADEMY_AI_API_KEY")
        self.model = model or os.getenv("SHYAM_ACADEMY_AI_MODEL")
        self.base_url = (base_url or os.getenv(
            "SHYAM_ACADEMY_AI_BASE_URL", "https://api.openai.com/v1"
        )).rstrip("/")
        self.timeout = timeout
        if not self.api_key:
            raise RealProviderError("Real AI provider API key is not configured.")
        if not self.model:
            raise RealProviderError("Real AI provider model is not configured.")

    def _chat(self, prompt):
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }).encode("utf-8")
        try:
            with request.urlopen(
                request.Request(
                    f"{self.base_url}/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                ),
                timeout=self.timeout,
            ) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            if exc.code == 401:
                raise RealProviderError("AI provider authentication failed.") from exc
            if exc.code == 429:
                raise RealProviderError("AI provider rate limit reached.") from exc
            if 500 <= exc.code:
                raise RealProviderError("AI provider is temporarily unavailable.") from exc
            raise RealProviderError("AI provider rejected the request.") from exc
        except (error.URLError, TimeoutError) as exc:
            raise RealProviderError("AI provider network request failed.") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RealProviderError("AI provider returned malformed data.") from exc
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RealProviderError("AI provider returned a malformed response.") from exc
        if not isinstance(content, str) or not content.strip():
            raise RealProviderError("AI provider returned an empty response.")
        return content

    def generate_advanced(self, task_type, prompt):
        return self._chat(
            f"Task type: {task_type}\nReturn a concise, safe answer using only this request:\n{prompt}"
        )

    def generate_timetable(self, prompt):
        return self._chat(
            "Return only one JSON object for a validated learning timetable. "
            "Do not use Markdown or explanatory text. Include title, module_name, "
            "description, start_date, end_date, timezone, assumptions, and sessions "
            "with session_date, scheduled_time, category, topic, session_title, "
            f"prompt, day_number, and status.\n\nUser request:\n{prompt}"
        )

    def generate_routine(self, prompt):
        return self._chat(prompt)

    def generate_test(self, prompt):
        return self._chat(prompt)

    def evaluate_test_answer(self, prompt):
        return self._chat(prompt)

    def generate_interview(self, prompt):
        return self._chat(prompt)

    def evaluate_interview(self, prompt):
        return self._chat(prompt)

    def interview_action(self, prompt):
        return self._chat(prompt)

    def mentor_response(self, prompt):
        return self._chat(prompt)
