"""Back-compat import. Gemini is a wire on RemoteLLM, not a second client."""

from nightguard.adapter import RemoteLLM, project_to_contract

__all__ = ["GeminiLLM", "RemoteLLM", "project_to_contract"]


class GeminiLLM(RemoteLLM):
    def __init__(self, api_key: str, model: str | None = None) -> None:
        super().__init__(provider="gemini", api_key=api_key, model=model)
