"""OpenAI client used on the worker path."""

from openai import OpenAI

from app.config import settings


def generate_answer(query: str, api_key: str | None = None, model: str | None = None) -> str:
    key = api_key or settings.OPENAI_API_KEY
    if not key:
        raise ValueError("OPENAI_API_KEY is not configured")

    client = OpenAI(api_key=key, timeout=settings.OPENAI_TIMEOUT_SECONDS)
    response = client.chat.completions.create(
        model=model or settings.OPENAI_MODEL,
        max_tokens=settings.OPENAI_MAX_TOKENS,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a concise enterprise assistant. "
                    "Answer clearly for software and platform engineers."
                ),
            },
            {"role": "user", "content": query},
        ],
    )
    answer = response.choices[0].message.content
    if not answer or not answer.strip():
        raise ValueError("OpenAI returned an empty response")
    return answer.strip()
