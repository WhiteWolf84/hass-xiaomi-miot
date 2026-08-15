"""What real device specs actually produce, entity by entity.

`test_entity_naming` pins the rules; this pins the outcome. The tables below are
the whole visible contract of an integration reload: change a naming rule and
either these tables move -- deliberately, in the same commit -- or nothing does.

`unique_id` is the column that costs users the most. Home Assistant keys the
entity registry on it, so a changed unique_id is a brand new entity: the old one
goes stale and its history, automations and dashboard cards point at nothing.

Entity ids belong to Home Assistant, which composes them from the area, the
device and the entity name when the entity joins a platform. They are therefore
asserted against a real config entry at the bottom of this file, not against a
freshly constructed entity, where they are still None.

Every fixture is the spec as published by miot-spec.org, saved verbatim.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_TOKEN
from homeassistant.core import split_entity_id, valid_entity_id
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_miot import DOMAIN
from custom_components.xiaomi_miot import (  # noqa: F401
    binary_sensor, button, climate, cover, fan, humidifier, light,
    number, select, sensor, switch, text, time,
)
from custom_components.xiaomi_miot.core.device import Device

TRANSLATIONS = (
    Path(__file__).parents[1] / 'custom_components' / 'xiaomi_miot' / 'translations'
)

DOMAINS = [
    'binary_sensor', 'button', 'climate', 'cover', 'fan', 'humidifier',
    'light', 'number', 'select', 'sensor', 'switch', 'text', 'time',
]

# (domain, unique_id after the device's own prefix, name, translation_key)
DEHUMIDIFIER_ENTITIES = [
    ('button', '-info', None, 'info'),
    ('humidifier', '-2', None, 'dehumidifier'),
    ('light', '-5', 'Indicator Light', 'indicator_light'),
    ('number', '-delay-8.delay_time-2', 'Delay Delay Time', 'delay-delay_time'),
    ('select', '-indicator_light-5.mode-2', 'Indicator Light Mode', 'indicator_light-mode'),
    ('sensor', '-dehumidifier-2.fault-2', 'Dehumidifier Device Fault', 'dehumidifier-fault'),
    ('sensor', '-delay-8.delay_remain_time-3', 'Delay Delay Remain Time', 'delay-delay_remain_time'),
    ('sensor', '-environment-3.relative_humidity-1', 'Environment Relative Humidity', 'environment-relative_humidity'),
    ('sensor', '-environment-3.temperature-2', 'Environment Temperature', 'environment-temperature'),
    ('switch', '-alarm-4.alarm-1', 'Alarm', 'alarm-alarm'),
    ('switch', '-delay-8.delay-1', 'Delay', 'delay-delay'),
    ('switch', '-physical_controls_locked-6.physical_controls_locked-1', 'Physical Control Locked', 'physical_controls_locked-physical_controls_locked'),
]


def collect_entities(device):
    collected = {domain: [] for domain in DOMAINS}
    for domain, entities in collected.items():
        device.entry.adders[domain] = (
            lambda new, update_before_add=False, bucket=entities: bucket.extend(new)
        )
        device.add_entities(domain)
    return collected


def entity_rows(device):
    with patch('custom_components.xiaomi_miot.core.device.async_call_later'):
        entities = collect_entities(device)
    rows = sorted(
        (
            domain,
            entity.unique_id.replace(device.unique_id, ''),
            entity.name,
            entity.translation_key,
        )
        for domain, items in entities.items()
        for entity in items
    )
    pairs = [
        (domain, entity)
        for domain, items in entities.items()
        for entity in items
    ]
    return rows, pairs


def build(make_device, load_miot_spec, model, customizes=None):
    return make_device(
        load_miot_spec(f'{model}.json'), model=model, customizes=customizes,
    )


@pytest.mark.parametrize(
    ('model', 'expected'),
    [
        # the device type and the service agree, and nothing else claims the name
        ('xiaomi.derh.lite', 'dehumidifier'),
        # `device:switch` exposing three `service:switch`, one per gang: no gang
        # is the device, so none of them may drop its name
        ('lumi.switch.n3acn3', None),
        # `device:outlet` exposing `service:switch`: the names disagree, so the
        # rule declines to guess and the customize below is what decides
        ('chuangmi.plug.212a01', None),
    ],
)
def test_main_service_resolution(make_device, load_miot_spec, model, expected):
    device = build(make_device, load_miot_spec, model)
    main = device.main_service
    assert (main.name if main else None) == expected


def test_main_service_can_be_named_in_the_customizes(make_device, load_miot_spec):
    device = build(
        make_device, load_miot_spec, 'chuangmi.plug.212a01',
        customizes={'main_service': 'switch'},
    )
    assert device.main_service.name == 'switch'

    rows, _ = entity_rows(device)
    assert [row for row in rows if row[0] == 'switch'] == [
        ('switch', '-2', None, 'switch'),
    ]

    # the indicator light is a feature of the plug and keeps saying so
    assert [row[2] for row in rows if row[0] == 'light'] == ['Indicator Light']


def test_dehumidifier_entities(make_device, load_miot_spec):
    """Twelve entities, one of which *is* the device and so has no name."""
    device = build(make_device, load_miot_spec, 'xiaomi.derh.lite')
    rows, _ = entity_rows(device)
    assert rows == DEHUMIDIFIER_ENTITIES


def test_only_the_main_entity_stands_for_the_device(make_device, load_miot_spec):
    device = build(make_device, load_miot_spec, 'xiaomi.derh.lite')
    _, pairs = entity_rows(device)
    unnamed = [
        entity for _, entity in pairs
        if entity.name is None and not entity.translation_key
    ]
    assert unnamed == []

    main = [
        entity for _, entity in pairs
        if entity._miot_service is device.main_service and entity.name is None
    ]
    assert [entity.unique_id.replace(device.unique_id, '') for entity in main] == ['-2']


def test_every_gang_of_a_multi_gang_switch_keeps_its_name(make_device, load_miot_spec):
    device = build(make_device, load_miot_spec, 'lumi.switch.n3acn3')
    rows, _ = entity_rows(device)
    assert [row[2] for row in rows if row[0] == 'switch'] == [
        'Left Switch Service',
        'Middle Switch Service',
        'Right Switch Service',
    ]


@pytest.mark.parametrize(
    'model',
    ['xiaomi.derh.lite', 'lumi.switch.n3acn3', 'chuangmi.plug.212a01'],
)
def test_no_entity_claims_an_entity_id(make_device, load_miot_spec, model):
    """Setting `entity_id` opts the entity out of Home Assistant's naming.

    Home Assistant stores an integration supplied id as `suggested_object_id`,
    which wins over the area and device prefixed form and is handed straight
    back by "regenerate entity IDs". Leaving it unset is what keeps the entity
    id in step with the device and area the user has arranged.
    """
    device = build(make_device, load_miot_spec, model)
    _, pairs = entity_rows(device)
    assert [entity.entity_id for _, entity in pairs if entity.entity_id] == []


@pytest.mark.parametrize(
    'model',
    ['xiaomi.derh.lite', 'lumi.switch.n3acn3', 'chuangmi.plug.212a01'],
)
def test_unnamed_entities_are_named_by_a_translation(make_device, load_miot_spec, model):
    """An entity with no name of its own is either the device or translated.

    Nothing else may be nameless: outside a platform the spec fallback is all
    there is, so a None here that `en.json` does not answer would reach the user
    as a bare device name on a feature entity -- and, now that the entity id is
    derived from the name, as a bare device name in the entity id too.
    """
    device = build(make_device, load_miot_spec, model)
    with open(TRANSLATIONS / 'en.json', encoding='utf-8') as file:
        english = json.load(file)['entity']

    _, pairs = entity_rows(device)
    for domain, entity in pairs:
        if entity.name is not None:
            continue
        if entity._miot_service is not None and entity._miot_service is device.main_service:
            continue
        translated = english.get(domain, {}).get(entity.translation_key, {})
        assert translated.get('name'), f'{entity.unique_id} has no name anywhere'


def test_the_main_entity_must_not_be_given_a_name_by_a_translation():
    """A `name` for a main service would put the duplication back.

    The entity keeps its translation key -- that is what translates the state
    attributes -- so a translator adding a name under it would be overriding the
    deliberate absence of one.
    """
    main_service_keys = {
        'humidifier': ['humidifier', 'dehumidifier'],
        'fan': ['fan', 'air_purifier', 'air_fresh'],
        'climate': ['air_conditioner', 'heater', 'thermostat'],
        'light': ['light'],
        'switch': ['switch', 'outlet'],
    }
    for path in sorted(TRANSLATIONS.glob('*.json')):
        with path.open(encoding='utf-8') as file:
            entities = json.load(file).get('entity', {})
        for domain, keys in main_service_keys.items():
            for key in keys:
                named = entities.get(domain, {}).get(key, {}).get('name')
                assert not named, f'{path.name}: {domain}.{key} must have no name'


async def setup_dehumidifier(hass, load_miot_spec, device_name):
    """Run a real config entry so Home Assistant assigns the entity ids."""
    spec = load_miot_spec('xiaomi.derh.lite.json')
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            'did': 'test-device',
            'mac': '14:d8:81:9c:f5:9c',
            CONF_NAME: device_name,
            CONF_HOST: '127.0.0.1',
            CONF_TOKEN: '0' * 32,
            'model': 'xiaomi.derh.lite',
            'urn': spec.type,
        },
    )
    entry.add_to_hass(hass)

    async def async_init_from_fixture(device):
        device.spec = load_miot_spec('xiaomi.derh.lite.json')
        device.init_converters()

    with (
        patch.object(Device, 'async_init', async_init_from_fixture),
        patch('custom_components.xiaomi_miot.core.device.async_call_later'),
        patch(
            'custom_components.xiaomi_miot.SUPPORTED_DOMAINS',
            ['button', 'humidifier', 'light', 'number', 'select', 'sensor', 'switch'],
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = {
        item.unique_id: item.entity_id
        for item in registry.entities.values()
        if item.platform == DOMAIN
    }
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    return entry, entities


async def test_home_assistant_composes_the_entity_ids(hass, load_miot_spec):
    """The device name leads, and the main entity is the device name alone."""
    _, entities = await setup_dehumidifier(hass, load_miot_spec, 'Deumidificatore')
    by_id = sorted(entities.values())

    assert 'humidifier.deumidificatore' in by_id
    assert 'light.deumidificatore_indicator_light' in by_id
    # `en.json` names this one "Child Lock", and a translation outranks the
    # spec for the entity id exactly as it does for the friendly name
    assert 'switch.deumidificatore_child_lock' in by_id
    assert 'button.deumidificatore_info' in by_id

    for entity_id in by_id:
        assert valid_entity_id(entity_id), entity_id
        assert split_entity_id(entity_id)[1].startswith('deumidificatore'), entity_id


async def test_a_renamed_device_leads_the_entity_ids_of_a_fresh_install(
    hass, load_miot_spec,
):
    """Nothing of the model or the MAC survives in the id any more."""
    _, entities = await setup_dehumidifier(hass, load_miot_spec, 'Camera')

    assert 'humidifier.camera' in entities.values()
    assert not [
        entity_id for entity_id in entities.values()
        if 'xiaomi_lite' in entity_id or 'f59c' in entity_id
    ]
