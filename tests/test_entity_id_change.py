"""Renaming an entity_id changes the entity in place.

Since Home Assistant 2026.11 an entity_id change no longer removes and re-adds
the entity, unless it belongs to a custom integration whose classes implement
an add or remove hook without `async_entity_id_changed`. That compatibility
path goes away in 2027.11.

Being re-added was not harmless here: `XEntity` subscribes to its device in the
constructor and unsubscribes when removed, so a renamed entity stopped updating
until Home Assistant restarted.
"""
import importlib

import pytest
from homeassistant.helpers import entity as ha_entity
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.setup import async_setup_component

from custom_components.xiaomi_miot import DOMAIN
from custom_components.xiaomi_miot.sensor import SensorEntity

PLATFORMS = [
    'alarm_control_panel', 'binary_sensor', 'button', 'camera', 'climate', 'cover',
    'device_tracker', 'fan', 'humidifier', 'light', 'media_player', 'number',
    'remote', 'select', 'sensor', 'switch', 'text', 'time', 'vacuum', 'water_heater',
]
# The platforms a dehumidifier like xiaomi.derh.lite is made of, which must be
# covered whatever optional libraries the test environment lacks.
REQUIRED = {'humidifier', 'sensor', 'switch', 'select'}


def _entity_classes():
    classes, imported = set(), set()
    for platform in PLATFORMS:
        try:
            module = importlib.import_module(f'custom_components.xiaomi_miot.{platform}')
        except ImportError:
            # camera and media_player need turbojpeg / pyhap
            continue
        imported.add(platform)
        todo = [
            obj for obj in vars(module).values()
            if isinstance(obj, type) and issubclass(obj, Entity)
        ]
        while todo:
            cls = todo.pop()
            if cls.__module__.startswith('custom_components.') and cls not in classes:
                classes.add(cls)
                todo.extend(cls.__subclasses__())
    assert REQUIRED <= imported
    return classes


def test_no_entity_class_is_re_added_on_an_entity_id_change():
    """Asks Home Assistant's own rule, which lives until 2027.11."""
    requires_readd = getattr(ha_entity, '_entity_class_requires_readd', None)
    if requires_readd is None:
        pytest.skip('the compatibility path is gone, every entity changes in place')
    re_added = sorted(
        cls.__qualname__ for cls in _entity_classes() if requires_readd(cls)
    )
    assert not re_added


async def _added_sensor(hass, make_device, load_miot_spec):
    """The thermostat's room temperature, added through the real platform."""
    device = make_device(
        load_miot_spec('cnhdm.airrtc.wkq01.json'),
        customizes={'sensor_properties': 'temperature'},
    )
    device.available = True
    conv = device.find_converter('sensor.environment.temperature')
    assert conv is not None
    sensor = SensorEntity(device, conv)
    assert await async_setup_component(hass, 'sensor', {})
    await hass.data['sensor'].async_add_entities([sensor])
    await hass.async_block_till_done()
    return device, conv, sensor


async def test_a_renamed_entity_keeps_its_device_updates(hass, make_device, load_miot_spec):
    device, conv, sensor = await _added_sensor(hass, make_device, load_miot_spec)
    old_id = sensor.entity_id
    assert old_id

    er.async_get(hass).async_update_entity(old_id, new_entity_id='sensor.renamed_room')
    await hass.async_block_till_done()

    assert sensor.entity_id == 'sensor.renamed_room'
    assert sensor.on_device_update in device.listeners
    assert hass.states.get(old_id) is None

    device.dispatch({conv.full_name: 21.5}, log=False)
    await hass.async_block_till_done()
    assert hass.states.get('sensor.renamed_room').state == '21.5'


async def test_a_renamed_entity_is_found_by_its_new_id(hass, make_device, load_miot_spec):
    """The integration's services resolve entity_id through this index."""
    _, _, sensor = await _added_sensor(hass, make_device, load_miot_spec)
    old_id = sensor.entity_id
    entities = hass.data[DOMAIN]['entities']
    assert entities[old_id] is sensor

    er.async_get(hass).async_update_entity(old_id, new_entity_id='sensor.renamed_room')
    await hass.async_block_till_done()

    assert entities['sensor.renamed_room'] is sensor
    assert old_id not in entities
