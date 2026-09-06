"""OpenAI client tests — mocked, no network."""

from unittest.mock import MagicMock, patch

import pytest

from app.llm import generate_answer


@patch("app.llm.OpenAI")
def test_generate_answer_returns_content(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="  Hello from OpenAI  "))]
    )

    answer = generate_answer("test query", api_key="sk-test", model="gpt-4o-mini")
    assert answer == "Hello from OpenAI"
    mock_openai_cls.assert_called_once_with(api_key="sk-test", timeout=60.0)


def test_generate_answer_requires_api_key():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        generate_answer("test query", api_key="")
