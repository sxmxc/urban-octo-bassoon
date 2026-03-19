from __future__ import annotations

import hashlib
import json
import random
import re
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from faker import Faker

from app.services.schema_contract import normalize_schema_for_builder


DEFAULT_MAX_ITEMS = 3
MOCKING_TEXT_LINES = [
    "mock payload delivered on time and with none of the warmth you were hoping for",
    "generated response approved by the schema and disappointed in your staging habits",
    "sample data polished just enough to fool a demo and roast a weak integration",
    "contract-safe mock output with the bedside manner of a failing health check",
    "schema-compliant response data returned with smug confidence and zero reassurance",
    "repeatable payload for tests, demos, and the next brave claim that it worked locally",
]
MOCKING_FIRST_NAMES = ["Blair", "Jordan", "Nova", "Parker", "Quinn", "Riley", "Sage"]
MOCKING_LAST_NAMES = ["Bennett", "Dryden", "Kestrel", "Mercer", "Reyes", "Sharpe", "Vale"]
MOCKING_COMPANIES = [
    "Deadline Theater",
    "Hard Reset Works",
    "Passive Aggressive Systems",
    "Probably Fine Labs",
    "Unsolicited Advice Group",
]
MOCKING_CITIES = ["Cedar Falls", "Harbor Point", "Summit Ridge", "Northfield", "Maple Grove"]
MOCKING_STATES = ["California", "Colorado", "New York", "Texas", "Washington"]
MOCKING_COUNTRIES = ["United States", "Canada", "United Kingdom", "Germany", "Australia"]
MOCKING_STREETS = ["125 Market Street", "42 Harbor Avenue", "18 Cedar Lane", "500 Summit Road", "77 Lakeview Drive"]
MOCKING_SLUG_PARTS = ["audit", "bird", "mock", "payload", "queue", "schema", "snark", "staging"]
MOCKING_PRICE_POINTS = [13.37, 42.42, 88.8, 101.01, 404.04]
MOCKING_INTEGERS = [7, 13, 42, 64, 101, 404, 418, 9001]
MOCKING_KEYBOARD_KEYS = [
    "Enter",
    "Escape",
    "Tab",
    "Space",
    "Backspace",
    "Delete",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "Shift",
    "Control",
    "Alt",
    "Meta",
    "F1",
    "F5",
    "F12",
    "A",
    "C",
    "K",
    "/",
]
MOCKING_SYSTEM_VERBS = [
    "Start",
    "Stop",
    "Restart",
    "Shutdown",
    "Halt",
    "Pause",
    "Resume",
    "Retry",
    "Cancel",
    "Enable",
    "Disable",
    "Start Job",
    "Restart Job",
    "Cancel Job",
    "Stop Job",
    "Archive",
    "Restore",
]
MOCKING_FILE_STEMS = [
    "backup",
    "catalog-export",
    "job-output",
    "payload-sample",
    "route-config",
    "session-log",
    "user-report",
]
MOCKING_FILE_EXTENSIONS = ["txt", "json", "csv", "log", "yaml", "pdf", "png"]
MOCKING_MIME_TYPES = [
    "application/json",
    "application/pdf",
    "application/xml",
    "application/zip",
    "image/jpeg",
    "image/png",
    "text/csv",
    "text/plain",
]
BCRYPT_ALPHABET = "./ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
MOCK_VALUE_TYPE_ALIASES = {
    "id": "uuid",
    "guid": "uuid",
    "uuid": "uuid",
    "name": "full_name",
    "full_name": "full_name",
    "fullname": "full_name",
    "longtext": "long_text",
    "keyboard": "keyboard_key",
    "keycap": "keyboard_key",
    "hotkey": "keyboard_key",
    "filename": "file_name",
    "mime": "mime_type",
    "contenttype": "mime_type",
    "mediatype": "mime_type",
    "systemverb": "verb",
}
TEMPLATE_EXPRESSION_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


@dataclass
class GenerationContext:
    rng: random.Random
    faker: Faker
    path_parameters: dict[str, str]
    query_parameters: dict[str, str]
    request_body: Any


def _stable_seed(identity: str, seed_key: str | None) -> int:
    if seed_key:
        material = f"{identity}:{seed_key}"
    else:
        material = f"{identity}:{random.SystemRandom().randrange(0, 2 ** 63)}"

    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def build_generation_context(
    identity: str,
    seed_key: str | None,
    path_parameters: dict[str, str] | None = None,
    query_parameters: dict[str, str] | None = None,
    request_body: Any = None,
) -> GenerationContext:
    seed = _stable_seed(identity, seed_key)
    rng = random.Random(seed)
    faker = Faker()
    faker.seed_instance(rng.randint(0, 2 ** 31 - 1))
    return GenerationContext(
        rng=rng,
        faker=faker,
        path_parameters=dict(path_parameters or {}),
        query_parameters=dict(query_parameters or {}),
        request_body=deepcopy(request_body),
    )


def _coerce_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return default


def _coerce_float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _pick_generator(schema: dict[str, Any]) -> str | None:
    mock_config = schema.get("x-mock", {}) if isinstance(schema, dict) else {}
    value_type = mock_config.get("type") or mock_config.get("generator")
    if value_type:
        normalized = MOCK_VALUE_TYPE_ALIASES.get(str(value_type).strip().lower(), str(value_type).strip().lower())
        if normalized:
            return normalized

    schema_format = str(schema.get("format", "")).lower()
    if schema.get("enum"):
        return "enum"
    if schema_format == "email":
        return "email"
    if schema_format in {"uri", "url"}:
        return "url"
    if schema_format == "uuid":
        return "uuid"
    if schema_format == "date":
        return "date"
    if schema_format == "date-time":
        return "datetime"
    if schema_format == "time":
        return "time"
    schema_type = str(schema.get("type", "")).lower()
    if schema_type == "integer":
        return "integer"
    if schema_type == "number":
        return "number"
    if schema_type == "boolean":
        return "boolean"
    return None


def _mock_mode(schema: dict[str, Any]) -> str:
    if not isinstance(schema, dict):
        return "generate"
    mock_config = schema.get("x-mock", {}) if isinstance(schema.get("x-mock"), dict) else {}
    mode = str(mock_config.get("mode", "generate")).lower()
    return mode if mode in {"fixed", "generate", "mocking"} else "generate"


def _is_mocking_mode(schema: dict[str, Any]) -> bool:
    return _mock_mode(schema) == "mocking"


def _linked_path_parameter(schema: dict[str, Any]) -> str | None:
    if not isinstance(schema, dict):
        return None

    mock_config = schema.get("x-mock", {}) if isinstance(schema.get("x-mock"), dict) else {}
    value_type = str(mock_config.get("type") or mock_config.get("generator") or "").strip().lower()
    if value_type != "path_parameter":
        return None

    direct_parameter = mock_config.get("parameter")
    if isinstance(direct_parameter, str) and direct_parameter.strip():
        return direct_parameter.strip()

    options = mock_config.get("options", {}) if isinstance(mock_config.get("options"), dict) else {}
    option_parameter = options.get("parameter")
    if isinstance(option_parameter, str) and option_parameter.strip():
        return option_parameter.strip()

    return None


def _default_path_parameter_value(parameter_name: str) -> str:
    return f"sample-{parameter_name}"


def _coerce_linked_path_parameter(schema: dict[str, Any], raw_value: str) -> Any:
    schema_type = str(schema.get("type", "string")).lower()

    if schema_type == "integer":
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return 0

    if schema_type == "number":
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return 0.0

    if schema_type == "boolean":
        normalized = raw_value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return bool(normalized)

    return raw_value


def _mocking_slug(context: GenerationContext, words: int = 3) -> str:
    return "-".join(context.rng.choice(MOCKING_SLUG_PARTS) for _ in range(max(words, 1)))


def _fake_bcrypt_hash(context: GenerationContext, *, cost: int = 12) -> str:
    # Bcrypt hashes are 60 chars: "$2b$" + two-digit cost + "$" + 53 chars.
    body = "".join(context.rng.choice(BCRYPT_ALPHABET) for _ in range(53))
    return f"$2b${cost:02d}${body}"


def _mock_file_name(context: GenerationContext) -> str:
    stem = context.rng.choice(MOCKING_FILE_STEMS)
    extension = context.rng.choice(MOCKING_FILE_EXTENSIONS)
    return f"{stem}.{extension}"


def _generate_string(schema: dict[str, Any], context: GenerationContext) -> str:
    generator = _pick_generator(schema) or "text"
    options = schema.get("x-mock", {}).get("options", {})
    min_length = max(_coerce_int(schema.get("minLength"), 0), 0)
    default_max_length = max(min_length, 280 if generator == "long_text" else 60 if generator == "password" else 48)
    max_length = max(_coerce_int(schema.get("maxLength"), default_max_length), min_length)
    mocking_mode = _is_mocking_mode(schema)

    if generator == "enum" and schema.get("enum"):
        return str(context.rng.choice(schema["enum"]))

    if mocking_mode and generator == "email":
        value = f"{_mocking_slug(context, 2).replace('-', '.')}@artificer.test"
    elif mocking_mode and generator == "username":
        value = f"{context.rng.choice(MOCKING_FIRST_NAMES).lower()}.{context.rng.choice(MOCKING_LAST_NAMES).lower()}"
    elif mocking_mode and generator == "password":
        value = _fake_bcrypt_hash(context)
    elif generator == "keyboard_key":
        value = context.rng.choice(MOCKING_KEYBOARD_KEYS)
    elif generator == "verb":
        value = context.rng.choice(MOCKING_SYSTEM_VERBS)
    elif mocking_mode and generator == "url":
        value = f"https://artificer.test/{_mocking_slug(context, 3)}"
    elif generator == "file_name":
        value = _mock_file_name(context)
    elif generator == "mime_type":
        value = context.rng.choice(MOCKING_MIME_TYPES)
    elif mocking_mode and generator == "uuid":
        value = str(context.faker.uuid4())
    elif mocking_mode and generator == "slug":
        words = max(_coerce_int(options.get("words"), 3), 1)
        value = _mocking_slug(context, words)
    elif mocking_mode and generator == "date":
        value = str(context.faker.date_object())
    elif mocking_mode and generator == "datetime":
        value = context.faker.date_time().isoformat()
    elif mocking_mode and generator == "time":
        value = context.faker.time()
    elif mocking_mode and generator == "first_name":
        value = context.rng.choice(MOCKING_FIRST_NAMES)
    elif mocking_mode and generator == "last_name":
        value = context.rng.choice(MOCKING_LAST_NAMES)
    elif mocking_mode and generator == "full_name":
        value = f"{context.rng.choice(MOCKING_FIRST_NAMES)} {context.rng.choice(MOCKING_LAST_NAMES)}"
    elif mocking_mode and generator == "company":
        value = context.rng.choice(MOCKING_COMPANIES)
    elif mocking_mode and generator == "phone":
        value = f"(555) 01{context.rng.randint(10, 99)}-{context.rng.randint(1000, 9999)}"
    elif mocking_mode and generator == "street_address":
        value = context.rng.choice(MOCKING_STREETS)
    elif mocking_mode and generator == "city":
        value = context.rng.choice(MOCKING_CITIES)
    elif mocking_mode and generator == "state":
        value = context.rng.choice(MOCKING_STATES)
    elif mocking_mode and generator == "country":
        value = context.rng.choice(MOCKING_COUNTRIES)
    elif mocking_mode and generator == "postal_code":
        value = f"{context.rng.randint(10000, 99999)}"
    elif mocking_mode and generator == "avatar_url":
        value = f"https://api.dicebear.com/7.x/fun-emoji/svg?seed={_mocking_slug(context, 2)}"
    elif mocking_mode:
        default_sentences = 2 if generator == "long_text" else 1
        sentences = max(_coerce_int(options.get("sentences"), default_sentences), 1)
        value = " ".join(context.rng.choice(MOCKING_TEXT_LINES) for _ in range(sentences))
    elif generator == "email":
        value = context.faker.email()
    elif generator == "username":
        value = context.faker.user_name()
    elif generator == "password":
        value = _fake_bcrypt_hash(context)
    elif generator == "keyboard_key":
        value = context.rng.choice(MOCKING_KEYBOARD_KEYS)
    elif generator == "verb":
        value = context.rng.choice(MOCKING_SYSTEM_VERBS)
    elif generator == "url":
        value = context.faker.url()
    elif generator == "file_name":
        value = _mock_file_name(context)
    elif generator == "mime_type":
        value = context.rng.choice(MOCKING_MIME_TYPES)
    elif generator == "uuid":
        value = str(context.faker.uuid4())
    elif generator == "slug":
        words = max(_coerce_int(options.get("words"), 3), 1)
        value = "-".join(context.faker.words(nb=words))
    elif generator == "date":
        value = str(context.faker.date_object())
    elif generator == "datetime":
        value = context.faker.date_time().isoformat()
    elif generator == "time":
        value = context.faker.time()
    elif generator == "first_name":
        value = context.faker.first_name()
    elif generator == "last_name":
        value = context.faker.last_name()
    elif generator == "full_name":
        value = context.faker.name()
    elif generator == "company":
        value = context.faker.company()
    elif generator == "phone":
        value = context.faker.phone_number()
    elif generator == "street_address":
        value = context.faker.street_address()
    elif generator == "city":
        value = context.faker.city()
    elif generator == "state":
        value = context.faker.state()
    elif generator == "country":
        value = context.faker.country()
    elif generator == "postal_code":
        value = context.faker.postcode()
    elif generator == "avatar_url":
        seed = context.faker.uuid4()
        value = f"https://api.dicebear.com/7.x/fun-emoji/svg?seed={seed}"
    else:
        default_sentences = 3 if generator == "long_text" else 1
        sentences = max(_coerce_int(options.get("sentences"), default_sentences), 1)
        value = " ".join(context.faker.sentences(nb=sentences)).strip()

    if len(value) < min_length:
        filler = context.faker.lexify(text="?" * (min_length - len(value)))
        value = f"{value}{filler}"

    return value[:max_length]


def _apply_template_string_constraints(schema: dict[str, Any], value: str, context: GenerationContext) -> str:
    min_length = max(_coerce_int(schema.get("minLength"), 0), 0)
    raw_max_length = schema.get("maxLength")
    max_length = None
    if isinstance(raw_max_length, (int, float)) and not isinstance(raw_max_length, bool):
        max_length = max(_coerce_int(raw_max_length, min_length), min_length)

    if len(value) < min_length:
        filler = context.faker.lexify(text="?" * (min_length - len(value)))
        value = f"{value}{filler}"

    if max_length is not None:
        return value[:max_length]
    return value


def _generate_integer(schema: dict[str, Any], context: GenerationContext) -> int:
    if schema.get("enum"):
        return int(context.rng.choice(schema["enum"]))

    minimum = _coerce_int(schema.get("minimum"), 0)
    maximum = _coerce_int(schema.get("maximum"), max(minimum, 999))
    if maximum < minimum:
        maximum = minimum

    if _is_mocking_mode(schema):
        candidates = [value for value in MOCKING_INTEGERS if minimum <= value <= maximum]
        if candidates:
            return context.rng.choice(candidates)

    return context.rng.randint(minimum, maximum)


def _generate_number(schema: dict[str, Any], context: GenerationContext) -> float:
    if schema.get("enum"):
        return float(context.rng.choice(schema["enum"]))

    options = schema.get("x-mock", {}).get("options", {})
    generator = _pick_generator(schema) or "float"
    minimum = _coerce_float(schema.get("minimum"), 0.0)
    maximum = _coerce_float(schema.get("maximum"), max(minimum, 999.99))
    if maximum < minimum:
        maximum = minimum

    if _is_mocking_mode(schema):
        preferred = [value for value in MOCKING_PRICE_POINTS if minimum <= value <= maximum]
        if preferred:
            if generator == "price":
                precision = max(_coerce_int(options.get("precision"), 2), 0)
                quantize_pattern = Decimal("1") if precision == 0 else Decimal(f"1.{'0' * precision}")
                return float(Decimal(str(context.rng.choice(preferred))).quantize(quantize_pattern))
            return float(context.rng.choice(preferred))

    if generator == "price":
        precision = max(_coerce_int(options.get("precision"), 2), 0)
        value = Decimal(str(context.rng.uniform(minimum or 1.0, maximum or 999.99)))
        quantize_pattern = Decimal("1") if precision == 0 else Decimal(f"1.{'0' * precision}")
        return float(value.quantize(quantize_pattern))

    return round(context.rng.uniform(minimum, maximum), 2)


def _generate_boolean(context: GenerationContext) -> bool:
    return bool(context.rng.randint(0, 1))


def _generate_object(schema: dict[str, Any], context: GenerationContext) -> dict[str, Any]:
    properties = schema.get("properties", {}) or {}
    property_order = list(schema.get("x-builder", {}).get("order", []) or [])
    for key in properties.keys():
        if key not in property_order:
            property_order.append(key)

    return {
        property_name: generate_value(properties[property_name], context)
        for property_name in property_order
        if property_name in properties
    }


def _generate_array(schema: dict[str, Any], context: GenerationContext) -> list[Any]:
    items = schema.get("items") or {"type": "string"}
    min_items = max(_coerce_int(schema.get("minItems"), 1), 0)
    max_items = max(_coerce_int(schema.get("maxItems"), max(min_items, DEFAULT_MAX_ITEMS)), min_items)
    count = context.rng.randint(min_items, max_items)
    return [generate_value(items, context) for _ in range(count)]


def _template_string(schema: dict[str, Any]) -> str | None:
    if not isinstance(schema, dict):
        return None
    mock_config = schema.get("x-mock", {}) if isinstance(schema.get("x-mock"), dict) else {}
    template = mock_config.get("template")
    if not isinstance(template, str):
        return None
    stripped = template.strip()
    return stripped or None


def _lookup_template_path(value: Any, segments: list[str]) -> Any:
    current = value
    for segment in segments:
        if isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
            continue

        if isinstance(current, list):
            try:
                index = int(segment)
            except (TypeError, ValueError):
                return None
            if index < 0 or index >= len(current):
                return None
            current = current[index]
            continue

        return None

    return current


def _stringify_template_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), default=str)
    return str(value)


def _resolve_template_token(token: str, *, base_value: Any, context: GenerationContext) -> Any:
    normalized = token.strip()
    if normalized == "value":
        return base_value

    parts = [segment.strip() for segment in normalized.split(".") if segment.strip()]
    if len(parts) < 3 or parts[0] != "request":
        return None

    location = parts[1]
    remainder = parts[2:]
    if location == "path":
        return _lookup_template_path(context.path_parameters, remainder)
    if location == "query":
        return _lookup_template_path(context.query_parameters, remainder)
    if location == "body":
        return _lookup_template_path(context.request_body, remainder)
    return None


def _render_template_string(template: str, *, base_value: Any, schema: dict[str, Any], context: GenerationContext) -> str:
    rendered = TEMPLATE_EXPRESSION_PATTERN.sub(
        lambda match: _stringify_template_value(
            _resolve_template_token(match.group(1), base_value=base_value, context=context)
        ),
        template,
    )
    return _apply_template_string_constraints(schema, rendered, context)


def render_templated_value(schema: Any, value: Any, context: GenerationContext) -> Any:
    if not isinstance(schema, dict):
        return value

    if (schema.get("type") == "object" or "properties" in schema) and isinstance(value, dict):
        properties = schema.get("properties", {}) or {}
        return {
            key: render_templated_value(properties.get(key), child_value, context)
            for key, child_value in value.items()
        }

    if (schema.get("type") == "array" or "items" in schema) and isinstance(value, list):
        item_schema = schema.get("items") or {"type": "string"}
        return [render_templated_value(item_schema, item, context) for item in value]

    template = _template_string(schema)
    if template is not None and isinstance(value, str):
        return _render_template_string(template, base_value=value, schema=schema, context=context)

    return value


def generate_value(schema: Any, context: GenerationContext) -> Any:
    if not isinstance(schema, dict):
        return deepcopy(schema)

    linked_parameter = _linked_path_parameter(schema)
    if linked_parameter:
        raw_value = context.path_parameters.get(linked_parameter, _default_path_parameter_value(linked_parameter))
        return _coerce_linked_path_parameter(schema, raw_value)

    mock_config = schema.get("x-mock", {}) or {}
    if mock_config.get("mode") == "fixed" and "value" in mock_config:
        return deepcopy(mock_config["value"])

    if "const" in schema:
        return deepcopy(schema["const"])

    schema_type = schema.get("type")

    if schema_type == "object" or "properties" in schema:
        return _generate_object(schema, context)

    if schema_type == "array" or "items" in schema:
        return _generate_array(schema, context)

    if schema_type == "integer":
        return _generate_integer(schema, context)

    if schema_type == "number":
        return _generate_number(schema, context)

    if schema_type == "boolean":
        return _generate_boolean(context)

    return _generate_string(schema, context)


def preview_from_schema(
    response_schema: dict[str, Any] | None,
    *,
    identity: str,
    path_parameters: dict[str, str] | None = None,
    query_parameters: dict[str, str] | None = None,
    request_body: Any = None,
    seed_key: str | None,
) -> Any:
    context = build_generation_context(
        identity,
        seed_key,
        path_parameters=path_parameters,
        query_parameters=query_parameters,
        request_body=request_body,
    )
    normalized_schema = normalize_schema_for_builder(response_schema or {}, property_name="root", include_mock=True)
    base_value = generate_value(normalized_schema, context)
    return render_templated_value(normalized_schema, base_value, context)
