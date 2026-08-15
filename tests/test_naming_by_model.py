"""What real device specs actually produce, entity by entity.

`test_entity_naming` pins the rules; this pins the outcome. The tables below are
the whole visible contract of an integration reload: change a naming rule and
either these tables move -- deliberately, in the same commit -- or nothing does.

`unique_id` is the column that costs users the most. Home Assistant keys the
entity registry on it, so a changed unique_id is a brand new entity: the old one
goes stale and its history, automations and dashboard cards point at nothing.
The entity ids sit next to it for the same reason.

Every fixture is the spec as published by miot-spec.org, saved verbatim.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.core import split_entity_id, valid_entity_id

from custom_components.xiaomi_miot import DOMAIN  # noqa: F401
from custom_components.xiaomi_miot import (  # noqa: F401
    binary_sensor, button, climate, cover, fan, humidifier, light,
    number, select, sensor, switch, text, time,
)

TRANSLATIONS = (
    Path(__file__).parents[1] / 'custom_components' / 'xiaomi_miot' / 'translations'
)

DOMAINS = [
    'binary_sensor', 'button', 'climate', 'cover', 'fan', 'humidifier',
    'light', 'number', 'select', 'sensor', 'switch', 'text', 'time',
]

# (domain, entity_id, unique_id after the device's own prefix, name, translation_key)
DEHUMIDIFIER_ENTITIES = [
    ('button', 'button.xiaomi_lite_eeff_info', '-info', None, 'info'),
    ('humidifier', 'humidifier.xiaomi_lite_eeff_dehumidifier', '-2', None, 'dehumidifier'),
    ('light', 'light.xiaomi_lite_eeff_indicator_light', '-5', 'Indicator Light', 'indicator_light'),
    ('number', 'number.xiaomi_lite_eeff_delay_time', '-delay-8.delay_time-2', 'Delay Delay Time', 'delay-delay_time'),
    ('select', 'select.xiaomi_lite_eeff_mode', '-indicator_light-5.mode-2', 'Indicator Light Mode', 'indicator_light-mode'),
    ('sensor', 'sensor.xiaomi_lite_eeff_delay_remain_time', '-delay-8.delay_remain_time-3', 'Delay Delay Remain Time', 'delay-delay_remain_time'),
    ('sensor', 'sensor.xiaomi_lite_eeff_device_fault', '-dehumidifier-2.fault-2', 'Dehumidifier Device Fault', 'dehumidifier-fault'),
    ('sensor', 'sensor.xiaomi_lite_eeff_relative_humidity', '-environment-3.relative_humidity-1', 'Environment Relative Humidity', 'environment-relative_humidity'),
    ('sensor', 'sensor.xiaomi_lite_eeff_temperature', '-environment-3.temperature-2', 'Environment Temperature', 'environment-temperature'),
    ('switch', 'switch.xiaomi_lite_eeff_alarm', '-alarm-4.alarm-1', 'Alarm', 'alarm-alarm'),
    ('switch', 'switch.xiaomi_lite_eeff_delay', '-delay-8.delay-1', 'Delay', 'delay-delay'),
    ('switch', 'switch.xiaomi_lite_eeff_physical_control_locked', '-physical_controls_locked-6.physical_controls_locked-1', 'Physical Control Locked', 'physical_controls_locked-physical_controls_locked'),
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
    return sorted(
        (
            domain,
            entity.entity_id,
            entity.unique_id.replace(device.unique_id, ''),
            entity.name,
            entity.translation_key,
        )
        for domain, items in entities.items()
        for entity in items
    ), [entity for items in entities.values() for entity in items]


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
    switches = [row for row in rows if row[0] == 'switch']
    assert switches == [('switch', 'switch.chuangmi_212a01_eeff_switch', '-2', None, 'switch')]

    # the indicator light is a feature of the plug and keeps saying so
    lights = [row for row in rows if row[0] == 'light']
    assert [row[3] for row in lights] == ['Indicator Light']


def test_dehumidifier_entities(make_device, load_miot_spec):
    """Twelve entities, one of which *is* the device and so has no name."""
    device = build(make_device, load_miot_spec, 'xiaomi.derh.lite')
    rows, _ = entity_rows(device)
    assert rows == DEHUMIDIFIER_ENTITIES


def test_only_the_main_entity_stands_for_the_device(make_device, load_miot_spec):
    device = build(make_device, load_miot_spec, 'xiaomi.derh.lite')
    _, entities = entity_rows(device)
    unnamed = [
        entity for entity in entities
        if entity.name is None and not entity.translation_key
    ]
    assert unnamed == []

    main = [
        entity for entity in entities
        if entity._miot_service is device.main_service and entity.name is None
    ]
    assert [entity.entity_id for entity in main] == [
        'humidifier.xiaomi_lite_eeff_dehumidifier',
    ]


def test_every_gang_of_a_multi_gang_switch_keeps_its_name(make_device, load_miot_spec):
    device = build(make_device, load_miot_spec, 'lumi.switch.n3acn3')
    rows, _ = entity_rows(device)
    assert [row[3] for row in rows if row[0] == 'switch'] == [
        'Left Switch Service',
        'Middle Switch Service',
        'Right Switch Service',
    ]


@pytest.mark.parametrize(
    'model',
    ['xiaomi.derh.lite', 'lumi.switch.n3acn3', 'chuangmi.plug.212a01'],
)
def test_entity_ids_are_valid_and_match_their_platform(make_device, load_miot_spec, model):
    """Home Assistant reports these two as errors from 2027.2 and 2027.5.

    Setting `entity_id` from the integration is allowed, but only where the id
    is well formed and lives in the platform's own domain.
    """
    device = build(make_device, load_miot_spec, model)
    rows, _ = entity_rows(device)
    for domain, entity_id, *_ in rows:
        assert valid_entity_id(entity_id), entity_id
        assert split_entity_id(entity_id)[0] == domain, entity_id


@pytest.mark.parametrize(
    'model',
    ['xiaomi.derh.lite', 'lumi.switch.n3acn3', 'chuangmi.plug.212a01'],
)
def test_unnamed_entities_are_named_by_a_translation(make_device, load_miot_spec, model):
    """An entity with no name of its own is either the device or translated.

    Nothing else may be nameless: outside a platform the spec fallback is all
    there is, so a None here that `en.json` does not answer would reach the user
    as a bare device name on a feature entity.
    """
    device = build(make_device, load_miot_spec, model)
    with open(TRANSLATIONS / 'en.json', encoding='utf-8') as file:
        english = json.load(file)['entity']

    _, entities = entity_rows(device)
    for entity in entities:
        if entity.name is not None:
            continue
        if entity._miot_service is not None and entity._miot_service is device.main_service:
            continue
        domain = split_entity_id(entity.entity_id)[0]
        translated = english.get(domain, {}).get(entity.translation_key, {})
        assert translated.get('name'), f'{entity.entity_id} has no name anywhere'


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
