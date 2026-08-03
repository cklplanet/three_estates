"""Reusable localization helpers for terminal text and LLM prompts.

Locale packs live under ``backend_server/locales/<locale>/``.  English source
prompts remain the final fallback, so adding a language never requires copying
every prompt at once.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from paths import BACKEND_ROOT, PROJECT_ROOT, resolve_backend_file


DEFAULT_LOCALE = "en-US"
LOCALES_ROOT = BACKEND_ROOT / "locales"


def _read_local_env_value(key):
    for env_path in (PROJECT_ROOT / ".env.local", PROJECT_ROOT / ".env"):
        if not env_path.is_file():
            continue
        with open(env_path, encoding="utf-8") as infile:
            for raw_line in infile:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                env_key, env_value = line.split("=", 1)
                if env_key.strip() == key:
                    return env_value.strip().strip('"').strip("'")
    return None


def normalize_locale(value):
    value = str(value or DEFAULT_LOCALE).strip().replace("_", "-")
    aliases = {
        "en": "en-US",
        "en-us": "en-US",
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh-hans": "zh-CN",
        "ja": "ja-JP",
        "ja-jp": "ja-JP",
        "jp": "ja-JP",
    }
    return aliases.get(value.casefold(), value)


ACTIVE_LOCALE = normalize_locale(
    os.getenv("THREE_ESTATES_LOCALE")
    or _read_local_env_value("THREE_ESTATES_LOCALE")
    or DEFAULT_LOCALE
)


def locale_chain(locale=None):
    locale = normalize_locale(locale or ACTIVE_LOCALE)
    candidates = [locale]
    language = locale.split("-", 1)[0]
    if language != locale:
        candidates.append(language)
    if DEFAULT_LOCALE not in candidates:
        candidates.append(DEFAULT_LOCALE)
    return candidates


@lru_cache(maxsize=None)
def _load_strings(locale):
    path = LOCALES_ROOT / locale / "strings.json"
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as infile:
        payload = json.load(infile)
    if not isinstance(payload, dict):
        raise ValueError(f"Locale strings must be a JSON object: {path}")
    return payload


def tr(key, default=None, locale=None, **kwargs):
    """Return a localized string with English and caller-default fallbacks."""
    for candidate in locale_chain(locale):
        value = _load_strings(candidate).get(key)
        if value is not None:
            break
    else:
        value = default if default is not None else key
    try:
        return str(value).format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return str(value)


def localized_prompt_path(prompt_template, locale=None):
    """Resolve a locale prompt override, falling back to the English source."""
    source_path = resolve_backend_file(prompt_template)
    filename = source_path.name
    for candidate in locale_chain(locale):
        override = LOCALES_ROOT / candidate / "prompts" / filename
        if override.is_file():
            return override
    return source_path


def prompt_language_instruction(locale=None):
    if normalize_locale(locale or ACTIVE_LOCALE) == DEFAULT_LOCALE:
        return ""
    return tr("prompt.language_instruction", locale=locale).strip()


def localized_prompt_data(data, locale=None):
    """Add reusable locale-specific policy fragments to prompt format data."""
    return {
        **data,
        "short_reasoning_limit": tr(
            "prompt.limit.short_reasoning",
            locale=locale,
        ),
        "movement_reasoning_limit": tr(
            "prompt.limit.movement_reasoning",
            locale=locale,
        ),
        "innate_profile_limit": tr(
            "prompt.limit.innate_profile",
            locale=locale,
        ),
        "relationship_limit": tr(
            "prompt.limit.relationship",
            locale=locale,
        ),
    }


def display_name(kind, canonical, locale=None):
    return tr(
        f"display.{kind}.{canonical}",
        default=str(canonical),
        locale=locale,
    )


def protocol_display_name(kind, canonical, locale=None):
    """Show a localized game term while retaining its canonical protocol ID."""
    localized = display_name(kind, canonical, locale=locale)
    if normalize_locale(locale or ACTIVE_LOCALE) == DEFAULT_LOCALE:
        return str(canonical)
    return tr(
        "display.protocol_label",
        locale=locale,
        localized=localized,
        canonical=canonical,
    )


def is_zh(locale=None):
    return normalize_locale(locale or ACTIVE_LOCALE).startswith("zh")
