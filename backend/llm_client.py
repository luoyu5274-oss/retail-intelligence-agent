"""DeepSeek API client (OpenAI-compatible)."""
import json
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        base = DEEPSEEK_BASE_URL.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=base)
    return _client


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 2048) -> str:
    client = get_client()
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def extract_json(messages: list[dict], max_tokens: int = 4096) -> dict | list:
    """Call LLM and parse JSON from the response."""
    client = get_client()
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=messages,
        temperature=0.1,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        return {}
