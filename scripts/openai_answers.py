"""OpenAI Responses transport with no automatic retries."""
import logging
import os

from dotenv import dotenv_values
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, OpenAI

from .answering import AnswerError
from .retrieval import ROOT


class OpenAIProvider:
    def __init__(self, settings):
        self.settings = settings

    def generate(self, request):
        # Keep diagnostics under this module's control and emit only fixed error codes.
        for name, logger in logging.root.manager.loggerDict.copy().items():
            if name.split(".")[0] in ("openai", "httpx", "httpcore", "httpx2", "httpcore2"):
                if isinstance(logger, logging.Logger):
                    logger.disabled = True
        key = dotenv_values(ROOT / ".env", encoding="utf-8-sig", interpolate=False).get("OPENAI_API_KEY")
        key = key or os.environ.get("OPENAI_API_KEY")
        if not key or not key.isascii() or any(character.isspace() for character in key):
            raise AnswerError("api_key_missing_or_invalid", request_sent=False)
        if key in request["input"]:
            raise AnswerError("invalid_input", request_sent=False)
        try:
            with OpenAI(api_key=key, base_url="https://api.openai.com/v1",
                        max_retries=0, timeout=self.settings["timeout_seconds"]) as client:
                response = client.responses.create(**request)
        except APITimeoutError:
            raise AnswerError("timeout") from None
        except APIStatusError as error:
            codes = {401: "authentication", 403: "permission_denied", 429: "rate_limit",
                     402: "insufficient_quota", 404: "model_unavailable", 408: "timeout"}
            code = codes.get(error.status_code, "provider_http_error")
            if error.code in ("insufficient_quota", "billing_hard_limit_reached"):
                code = "insufficient_quota"
            raise AnswerError(code) from None
        except APIConnectionError:
            raise AnswerError("connection_error") from None
        except APIError:
            raise AnswerError("provider_error") from None
        except ValueError:
            raise AnswerError("invalid_output") from None

        usage_data = getattr(response, "usage", None)
        usage = usage_data.model_dump(mode="json") if usage_data else None
        if response.status == "incomplete":
            reason = getattr(response.incomplete_details, "reason", None)
            code = "output_token_limit" if reason == "max_output_tokens" else "incomplete_output"
            raise AnswerError(code, usage)
        if getattr(response, "status", None) != "completed" or not response.output:
            raise AnswerError("invalid_output", usage)
        parts = [part for item in response.output if item.type == "message" for part in item.content]
        if any(part.type == "refusal" for part in parts):
            raise AnswerError("refusal", usage)
        raw = response.output_text
        if not raw or key in raw:
            raise AnswerError("invalid_output", usage)
        return raw, usage
