import dataclasses
import enum

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


def test_schema_maps_list_of_scalars_to_array_with_items():
    def send(tags: list[str]) -> None:
        pass

    schema = FunctionTool(send).schema()
    assert schema["properties"]["tags"] == {
        "type": "array",
        "items": {"type": "string"},
    }


def test_schema_unwraps_optional_to_the_inner_type():
    def send(limit: int | None = None) -> None:
        pass

    schema = FunctionTool(send).schema()
    assert schema["properties"]["limit"] == {"type": "integer"}
    assert "limit" not in schema["required"]


def test_schema_maps_enum_to_a_typed_enum_list():
    class Priority(enum.Enum):
        LOW = "low"
        HIGH = "high"

    def send(priority: Priority) -> None:
        pass

    schema = FunctionTool(send).schema()
    assert schema["properties"]["priority"] == {
        "type": "string",
        "enum": ["low", "high"],
    }


def test_schema_maps_nested_dataclass_to_a_nested_object():
    @dataclasses.dataclass
    class Address:
        city: str
        zip_code: str | None = None

    @dataclasses.dataclass
    class Customer:
        name: str
        address: Address

    def send(customer: Customer) -> None:
        pass

    schema = FunctionTool(send).schema()
    customer_schema = schema["properties"]["customer"]
    assert customer_schema["type"] == "object"
    assert customer_schema["required"] == ["name", "address"]
    assert customer_schema["properties"]["address"] == {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "zip_code": {"type": "string"},
        },
        "required": ["city"],
    }


def test_schema_still_defaults_bare_list_and_dict_and_unknown_types():
    class Unrecognized:
        pass

    def send(items: list, meta: dict, thing: Unrecognized) -> None:
        pass

    schema = FunctionTool(send).schema()
    assert schema["properties"]["items"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert schema["properties"]["meta"] == {"type": "object"}
    assert schema["properties"]["thing"] == {"type": "string"}
