"""The `language:` dictionary must actually reach MIoT spec names.

Entity names come from the spec, not from translations/*.json: MiotService and
MiotProperty resolve `friendly_desc` through TRANSLATION_LANGUAGES in their
constructor. That makes ordering load bearing — the dictionary has to be merged
before any spec is built, which is what async_reload_integration_config does.
"""
import json
from pathlib import Path

import pytest

from custom_components.xiaomi_miot.core import translation_languages as tl
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec

FIXTURE = Path('tests/fixtures/cnhdm.airrtc.wkq01.json')


@pytest.fixture
def restore_languages():
    original = {k: (dict(v) if isinstance(v, dict) else v) for k, v in tl.TRANSLATION_LANGUAGES.items()}
    yield
    tl.TRANSLATION_LANGUAGES.clear()
    tl.TRANSLATION_LANGUAGES.update(original)


def _descs(hass):
    spec = MiotSpec(hass, json.loads(FIXTURE.read_text(encoding='utf-8')))
    out = {}
    for srv in spec.services.values():
        out[srv.friendly_desc] = [p.friendly_desc for p in srv.properties.values()]
    return out


def test_italian_dictionary_exists():
    it = tl.TRANSLATION_LANGUAGES.get('it')
    assert isinstance(it, dict)
    assert it['_globals']['indicator light'] == 'Spia luminosa'
    assert it['environment']['environment temperature'] == 'Temperatura ambiente'


async def test_language_merge_translates_spec_names(hass, restore_languages):
    """Merging the `it` dictionary the way async_reload_integration_config does
    must change the names the entities end up showing."""
    before = _descs(hass)
    assert 'Environment' in ' '.join(before) or before

    tl.TRANSLATION_LANGUAGES.update(tl.TRANSLATION_LANGUAGES['it'])
    after = _descs(hass)

    assert after != before, 'the language merge had no effect on spec names'


async def test_globals_reach_property_names(hass, restore_languages):
    """A `_globals` entry must win over the raw English description."""
    tl.TRANSLATION_LANGUAGES.update(tl.TRANSLATION_LANGUAGES['it'])
    joined = []
    for srv, props in _descs(hass).items():
        joined.append(srv)
        joined += props
    text = ' | '.join(joined)
    # at least one known translation must be visible in this device's spec
    assert any(word in text for word in ('Temperatura', 'Modalità', 'Interruttore', 'Guasto')), text


@pytest.mark.parametrize(
    ('tag', 'expected_key'),
    [
        ('it', 'it'),
        ('zh-Hans', 'zh'),   # HA reports a region, the dictionaries do not carry one
        ('zh-Hant', 'zh'),
        ('de', 'de'),
        ('pt-BR', None),     # no Portuguese dictionary: names stay in English
        ('ja', None),
        ('', None),
    ],
)
def test_dictionary_selection_from_ha_language(tag, expected_key):
    from custom_components.xiaomi_miot import select_translation_dictionary

    got = select_translation_dictionary(tag)
    expected = tl.TRANSLATION_LANGUAGES.get(expected_key) if expected_key else None
    assert got is expected


async def test_italian_ha_language_translates_without_yaml(hass, restore_languages):
    """An Italian Home Assistant must get Italian names with no YAML at all."""
    from custom_components.xiaomi_miot import async_reload_integration_config

    hass.config.language = 'it'
    hass.data.setdefault('xiaomi_miot', {})
    await async_reload_integration_config(hass, {})

    names = []
    for srv, props in _descs(hass).items():
        names.append(srv)
        names += props
    text = ' | '.join(names)
    assert 'Temperatura ambiente' in text, text
    assert 'Environment Temperature' not in text, text
