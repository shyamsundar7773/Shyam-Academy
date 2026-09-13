import json
import logging
import socket
import time
from urllib import error, request
from urllib.parse import urlparse

from ai.gateway import AIGateway, AIProviderError, ClassroomContext


class CloudflareProviderError(AIProviderError):
    """Safe, classified Cloudflare provider failure."""


logger = logging.getLogger(__name__)


def build_cloudflare_endpoint(base_url, account_id):
    base = (base_url or "").strip().rstrip("/")
    account = (account_id or "").strip()
    if not base:
        raise CloudflareProviderError("Cloudflare AI base URL is not configured.")
    if "{" in base or "}" in base:
        if not account:
            raise CloudflareProviderError("Cloudflare Account ID is not configured.")
        base = base.replace("{ACCOUNT_ID}", account)
    if "{ACCOUNT_ID}" in base or "{" in base or "}" in base:
        raise CloudflareProviderError("Cloudflare AI base URL contains an invalid placeholder.")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CloudflareProviderError("Cloudflare AI base URL is invalid.")
    if "/accounts/" not in parsed.path and not account:
        raise CloudflareProviderError("Cloudflare Account ID is not configured.")
    if not parsed.path.rstrip("/").endswith("/chat/completions"):
        base = base.rstrip("/") + "/chat/completions"
    return base


class CloudflareProvider(AIGateway):
    """Cloudflare Workers AI OpenAI-compatible chat-completions adapter."""

    def __init__(self, api_key=None, model=None, base_url=None, account_id=None, timeout=60):
        from config.bootstrap import get_config_value
        self.api_key = (
            get_config_value("SHYAM_ACADEMY_AI_API_KEY")
            if api_key is None else api_key
        )
        self.model = (
            get_config_value("SHYAM_ACADEMY_AI_MODEL")
            if model is None else model
        )
        self.account_id = (
            get_config_value("SHYAM_ACADEMY_AI_ACCOUNT_REFERENCE")
            if account_id is None else account_id
        )
        self.base_url = (
            get_config_value("SHYAM_ACADEMY_AI_BASE_URL")
            if base_url is None else base_url
        )
        self.timeout = timeout
        if not self.api_key:
            raise CloudflareProviderError("Cloudflare API token is not configured.")
        if not self.model:
            raise CloudflareProviderError("Cloudflare AI model is not configured.")
        self.endpoint = build_cloudflare_endpoint(self.base_url, self.account_id)

    def _chat(self, messages):
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096,
            "reasoning_effort": "low",
        }).encode("utf-8")
        started = time.monotonic()
        try:
            with request.urlopen(
                request.Request(
                    self.endpoint,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + self.api_key,
                    },
                ),
                timeout=self.timeout,
            ) as response:
                body = response.read().decode("utf-8")
                raw = json.loads(body)
                logger.debug(
                    "Cloudflare response status=%s duration_ms=%d keys=%s",
                    getattr(response, "status", 200),
                    int((time.monotonic() - started) * 1000),
                    sorted(raw.keys()) if isinstance(raw, dict) else type(raw).__name__,
                )
        except error.HTTPError as exc:
            logger.warning(
                "Cloudflare request failed category=http status=%s duration_ms=%d",
                exc.code, int((time.monotonic() - started) * 1000),
            )
            messages_by_code = {
                401: "Cloudflare API token authentication failed.",
                403: "Cloudflare API token is not authorized for this account or model.",
                404: "Cloudflare AI endpoint or model was not found.",
                429: "Cloudflare AI rate limit reached.",
            }
            raise CloudflareProviderError(
                messages_by_code.get(exc.code, "Cloudflare AI provider rejected the request.")
            ) from exc
        except (socket.timeout, TimeoutError) as exc:
            logger.warning(
                "Cloudflare request failed category=timeout timeout_seconds=%s duration_ms=%d",
                self.timeout, int((time.monotonic() - started) * 1000),
            )
            raise CloudflareProviderError(
                "Cloudflare AI network request timed out. Please try again."
            ) from exc
        except error.URLError as exc:
            logger.warning(
                "Cloudflare request failed category=network reason=%s duration_ms=%d",
                type(exc.reason).__name__ if exc.reason else "unknown",
                int((time.monotonic() - started) * 1000),
            )
            raise CloudflareProviderError("Cloudflare AI network request failed.") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CloudflareProviderError("Cloudflare AI returned malformed JSON.") from exc
        choice = None
        message = None
        try:
            choice = raw["choices"][0]
            message = choice["message"]
            content = message.get("content")
            if content is None:
                content = message.get("reasoning_content")
            logger.debug(
                "Cloudflare completion shape choices=%d message_keys=%s finish_reason=%s",
                len(raw["choices"]), sorted(message.keys()), choice.get("finish_reason"),
            )
        except (KeyError, IndexError, TypeError) as exc:
            if isinstance(raw, dict) and isinstance(raw.get("result"), dict):
                content = raw["result"].get("response")
            else:
                content = None
            if content is None:
                logger.warning("Cloudflare malformed response shape=%s", type(raw).__name__)
                raise CloudflareProviderError("Cloudflare AI returned a malformed response.") from exc
        if not isinstance(content, str) or not content.strip():
            logger.warning(
                "Cloudflare provider empty content model=%s duration_ms=%d "
                "finish_reason=%s reasoning_content_length=%d",
                self.model, int((time.monotonic() - started) * 1000),
                choice.get("finish_reason") if isinstance(locals().get("choice"), dict) else None,
                len(message.get("reasoning_content") or "")
                if isinstance(locals().get("message"), dict) else 0,
            )
            raise CloudflareProviderError("Cloudflare AI returned an empty response.")
        return content.strip()

    def generate_advanced(self, task_type, prompt):
        return self._chat([{"role": "system", "content": f"Task type: {task_type}. Return a safe answer."}, {"role": "user", "content": prompt}])

    def generate_timetable(self, prompt):
        return self._chat([
            {
                "role": "system",
                "content": (
                    "Create a validated learning timetable from the user request. "
                    "Return only one JSON object, with no Markdown or explanation. "
                    "Required top-level keys: title, module_name, description, "
                    "start_date, end_date, timezone, assumptions, sessions. "
                    "Each session requires session_date, scheduled_time, category, "
                    "topic, session_title, prompt, day_number, and status. "
                    "Use only these canonical categories: Today Learning, Level 1, "
                    "Level 2, Problem Solving, Test, "
                    "Interview Preparation, Interview Room. "
                    "Interpret subject phrases such as SQL Fundamental as a topic/module "
                    "under Level 1, not as a new category. Follow explicit requested "
                    "day counts within date windows and keep generated times inside "
                    "requested time ranges."
                ),
            },
            {"role": "user", "content": prompt},
        ])

    def generate_routine(self, prompt):
        return self._chat([{"role": "user", "content": prompt}])

    def generate_test(self, prompt):
        return self._chat([{"role": "user", "content": prompt}])

    def evaluate_test_answer(self, prompt):
        return self._chat([{"role": "user", "content": prompt}])

    def generate_interview(self, prompt):
        return self._chat([{"role": "user", "content": prompt}])

    def evaluate_interview(self, prompt):
        return self._chat([{"role": "user", "content": prompt}])

    def interview_action(self, prompt):
        return self._chat([{"role": "user", "content": prompt}])

    def mentor_response(self, prompt):
        return self._chat([{"role": "user", "content": prompt}])

    def generate_lesson(self, prompt, context: ClassroomContext):
        return self._chat([{"role": "system", "content": f"Teach {context.topic} using the supplied session context."}, {"role": "user", "content": prompt}])

    def ask_followup(self, prompt, context, lesson, history):
        return self._chat([{"role": "system", "content": f"Context: {context.topic}\nPrior lesson: {lesson}"}, *history[-8:], {"role": "user", "content": prompt}])

    def generate_explanation(self, context, lesson):
        return self._chat([{"role": "user", "content": f"Explain this lesson more simply:\n{lesson}"}])

    def generate_example(self, context, lesson):
        return self._chat([{"role": "user", "content": f"Give a practical example for:\n{lesson}"}])
