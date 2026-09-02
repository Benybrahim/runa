import pytest

from runa.tool import FunctionTool, Tool, tool


class WebSearch(Tool):
    """Search the web for a query."""

    def call(self, query: str, limit: int = 5) -> list[str]:
        return [f"result for {query}"] * limit


def test_class_tool_name_and_description_default_from_class():
    web_search = WebSearch()
    assert web_search.tool_name() == "WebSearch"
    assert web_search.tool_description() == "Search the web for a query."


def test_class_tool_schema_reflects_call_signature():
    schema = WebSearch().schema()
    assert schema["type"] == "object"
    assert schema["properties"]["query"] == {"type": "string"}
    assert schema["properties"]["limit"] == {"type": "integer"}
    assert schema["required"] == ["query"]


def test_class_tool_name_override():
    class Named(Tool):
        name = "custom_name"

        def call(self) -> None:
            pass

    assert Named().tool_name() == "custom_name"


def test_function_tool_wraps_plain_function():
    def get_weather(city: str) -> str:
        """Get the weather for a city."""
        return f"{city}: sunny"

    wrapped = FunctionTool(get_weather)
    assert wrapped.tool_name() == "get_weather"
    assert wrapped.tool_description() == "Get the weather for a city."
    assert wrapped.call(city="Tokyo") == "Tokyo: sunny"
    assert wrapped.schema()["properties"]["city"] == {"type": "string"}


def test_tool_decorator_returns_function_tool():
    @tool
    def get_weather(city: str) -> str:
        return f"{city}: sunny"

    assert isinstance(get_weather, FunctionTool)
    assert get_weather.call(city="Kyoto") == "Kyoto: sunny"


def test_tool_decorator_accepts_overrides():
    @tool(name="weather", requires_approval=True)
    def get_weather(city: str) -> str:
        return f"{city}: sunny"

    assert get_weather.tool_name() == "weather"
    assert get_weather.requires_approval is True


def test_base_tool_call_not_implemented():
    with pytest.raises(NotImplementedError):
        Tool().call()
