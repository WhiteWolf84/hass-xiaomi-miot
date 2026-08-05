"""Tests for bundled Xiaomi Miot translations."""
import json
from pathlib import Path

import pytest


TRANS_DIR = Path("custom_components/xiaomi_miot/translations")
TRANSLATIONS = sorted(path.name for path in TRANS_DIR.glob("*.json"))
REAUTH_STEPS = {"reauth_password", "reauth_verify", "reauth_captcha"}
ERROR_KEYS = {
    "invalid_auth",
    "need_verify",
    "need_captcha",
    "cannot_connect",
    "save_failed",
    "unknown",
}
ABORT_KEYS = {"unsupported_sid", "wrong_account", "reauth_successful"}


@pytest.mark.parametrize("name", TRANSLATIONS)
def test_translation_has_reauth_keys_without_legacy_micoapi(name):
    data = json.loads((TRANS_DIR / name).read_text(encoding="utf-8"))
    config = data.get("config") or {}
    steps = config.get("step") or {}

    assert not REAUTH_STEPS - set(steps)
    assert not ERROR_KEYS - set(config.get("error") or {})
    assert not ABORT_KEYS - set(config.get("abort") or {})
    assert "{verify_url}" in steps["reauth_verify"]["description"]
    assert "{captcha_image}" in steps["reauth_captcha"]["description"]

    option_steps = (data.get("options") or {}).get("step") or {}
    assert "micoapi" not in option_steps
    cloud = option_steps.get("cloud") or {}
    assert "micoapi_verify" not in (cloud.get("data") or {})
    assert "micoapi_verify" not in (cloud.get("data_description") or {})


def _flatten(obj, prefix=""):
    if not isinstance(obj, dict):
        return {prefix: obj}
    flat = {}
    for key, value in obj.items():
        flat.update(_flatten(value, f"{prefix}.{key}" if prefix else key))
    return flat


@pytest.mark.parametrize("name", TRANSLATIONS)
def test_translation_has_no_orphan_keys(name):
    """Every key in a locale must exist in en.json.

    A key the reference does not have is either a typo or a structural mistake
    (a value map missing its `state` level, say), and Home Assistant silently
    ignores it — the translation looks present but never renders.
    """
    reference = _flatten(json.loads((TRANS_DIR / "en.json").read_text(encoding="utf-8")))
    locale = _flatten(json.loads((TRANS_DIR / name).read_text(encoding="utf-8")))

    assert not set(locale) - set(reference)


def test_reference_locales_are_complete():
    """en.json and it.json are the maintained pair and must stay at full parity.

    The other locales are partial by nature — contributors fill them in over
    time — so they are deliberately not covered here.
    """
    reference = _flatten(json.loads((TRANS_DIR / "en.json").read_text(encoding="utf-8")))
    italian = _flatten(json.loads((TRANS_DIR / "it.json").read_text(encoding="utf-8")))

    assert not set(reference) - set(italian)

    # The customizing form used to ship the raw option names as their own labels
    # ("bind_sensor": "bind_sensor"), which reads as untranslated in every locale.
    prefix = "config.step.customizing.data."
    assert not [
        key
        for key, value in reference.items()
        if key.startswith(prefix) and value == key[len(prefix):]
    ]
