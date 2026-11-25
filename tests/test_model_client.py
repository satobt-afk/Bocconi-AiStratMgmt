"""Tests for the Ollama adapter, without calling a real model.

The client receives a fake `post` function, so we can check exactly what
would be sent over HTTP and how the answer is translated.
"""

import pytest

from backend.model_client import ModelUnavailable, OllamaClient, ToolCall

TOOLS = [{
    "name": "get_budget_status",
    "description": "Budget status of the current month.",
    "parameters": {"type": "object", "properties": {}},
}]


def make_client(response=None, error=None):
    sent = {}

    def fake_post(url, payload, timeout):
        sent["url"], sent["payload"] = url, payload
        if error:
            raise error
        return response

    return OllamaClient(model="qwen2.5:3b", url="http://localhost:11434", post=fake_post), sent


def test_request_uses_ollama_format():
    client, sent = make_client({"message": {"role": "assistant", "content": "Hi"}})

    client.chat([{"role": "user", "content": "Hello"}], TOOLS)

    assert sent["url"] == "http://localhost:11434/api/chat"
    assert sent["payload"]["model"] == "qwen2.5:3b"
    assert sent["payload"]["stream"] is False
    assert sent["payload"]["tools"][0] == {"type": "function", "function": TOOLS[0]}


def test_plain_answer_is_returned_as_text():
    client, _ = make_client({"message": {"role": "assistant", "content": "  Ciao!  "}})

    reply = client.chat([{"role": "user", "content": "Hello"}], TOOLS)

    assert reply.content == "Ciao!"
    assert reply.tool_calls == []


@pytest.mark.parametrize("arguments", [{"amount": 150}, '{"amount": 150}'])
def test_tool_calls_are_parsed_even_when_arguments_are_a_string(arguments):
    response = {"message": {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "can_afford", "arguments": arguments}}
    ]}}
    client, _ = make_client(response)

    reply = client.chat([{"role": "user", "content": "Can I?"}], TOOLS)

    assert reply.tool_calls == [ToolCall(id="call_0", name="can_afford", arguments={"amount": 150})]


def test_tool_results_are_sent_back_in_ollama_format():
    client, sent = make_client({"message": {"role": "assistant", "content": "Done"}})
    history = [
        {"role": "user", "content": "Status?"},
        {"role": "assistant", "content": "", "tool_calls": [ToolCall("call_0", "get_budget_status", {})]},
        {"role": "tool", "tool_call_id": "call_0", "name": "get_budget_status", "content": '{"spent": 10}'},
    ]

    client.chat(history, TOOLS)

    messages = sent["payload"]["messages"]
    assert messages[1]["tool_calls"] == [{"function": {"name": "get_budget_status", "arguments": {}}}]
    assert messages[2] == {"role": "tool", "tool_name": "get_budget_status", "content": '{"spent": 10}'}


def test_read_image_sends_the_image_to_the_vision_model_with_a_schema():
    sent = {}

    def fake_post(url, payload, timeout):
        sent["payload"] = payload
        return {"message": {"role": "assistant", "content": '{"total": 19.6}'}}

    client = OllamaClient(vision_model="qwen3-vl:2b-instruct", post=fake_post)
    schema = {"type": "object", "properties": {"total": {"type": "number"}}}

    result = client.read_image("Read it", "aW1hZ2U=", schema)

    assert result == {"total": 19.6}
    assert sent["payload"]["model"] == "qwen3-vl:2b-instruct"
    assert sent["payload"]["format"] == schema
    assert sent["payload"]["messages"][0]["images"] == ["aW1hZ2U="]


def test_read_image_with_invalid_json_returns_empty_dict():
    client = OllamaClient(post=lambda url, payload, timeout: {"message": {"content": "not json"}})

    assert client.read_image("Read it", "aW1hZ2U=", {}) == {}


def test_unreachable_server_raises_model_unavailable():
    client, _ = make_client(error=OSError("Connection refused"))

    with pytest.raises(ModelUnavailable):
        client.chat([{"role": "user", "content": "Hello"}], TOOLS)
