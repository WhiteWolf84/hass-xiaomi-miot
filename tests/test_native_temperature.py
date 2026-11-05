"""Climate and water heater entities report temperatures in the device's unit.

Home Assistant 2026.11 renamed the temperature members of both entity types with
a `native_` prefix (`current_temperature`, `target_temperature`,
`target_temperature_high/low`, `temperature_unit`, and their `_attr_`
shorthands). The base class converts them to the system unit itself. The old
names still work but warn: at import for a class that provides one, at runtime
for every read or write. They stop working in 2027.11.

`min_temp`, `max_temp` and `target_temperature_step` keep their names and stay
in the native unit.
"""
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from homeassistant.const import UnitOfTemperature
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from custom_components.xiaomi_miot import climate, water_heater

from .test_converter_options import make_climate

ROOT = Path(__file__).parents[1]
OLD_NAMES = (
    'current_temperature',
    'target_temperature',
    'target_temperature_high',
    'target_temperature_low',
    'temperature_unit',
)
OLD_USE = re.compile(
    r'(?:\b_attr_|\bself\.|\bdef )'
    r'(?:current_temperature|target_temperature(?:_high|_low)?|temperature_unit)\b'
)


def _with_subclasses(*classes):
    found = []
    todo = list(classes)
    while todo:
        cls = todo.pop()
        if cls not in found:
            found.append(cls)
            todo.extend(cls.__subclasses__())
    return found


def test_no_class_provides_the_old_names():
    """Providing one is what logs the warning at import. Home Assistant would
    also move a provided `_attr_` name into the class dict, so this catches it
    either way."""
    for cls in _with_subclasses(
        climate.BaseClimateEntity,
        climate.ClimateEntity,
        climate.MiirClimateEntity,
        water_heater.MiotWaterHeaterEntity,
    ):
        if not cls.__module__.startswith('custom_components.'):
            continue
        for name in OLD_NAMES:
            assert name not in cls.__dict__, (cls.__qualname__, name)
            assert f'_attr_{name}' not in cls.__dict__, (cls.__qualname__, name)


def test_the_source_never_reads_or_writes_the_old_names():
    """Reads and writes warn at runtime, so they are checked in the source."""
    for module in (climate, water_heater):
        source = Path(module.__file__).read_text(encoding='utf-8')
        assert not OLD_USE.findall(source), module.__name__


def test_importing_the_platforms_logs_no_deprecation():
    """The startup log is where the warnings showed up, so import the modules in
    a fresh interpreter and read what it logs. Home Assistant is imported first,
    as it has to be before httpx since 2026.11."""
    code = (
        'import logging\n'
        'import homeassistant\n'
        'logging.basicConfig(level=logging.WARNING)\n'
        'import custom_components.xiaomi_miot.config_flow\n'
        'import custom_components.xiaomi_miot.climate\n'
        'import custom_components.xiaomi_miot.water_heater\n'
    )
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    reported = [
        line for line in output.splitlines()
        if 'xiaomi_miot' in line and 'deprecated' in line.lower()
    ]
    assert not reported, reported


def _thermostat(make_device, load_miot_spec):
    """prop.2.10 switches the thermostat on, prop.2.8 is its target (°C, 5-50)."""
    return make_climate(
        make_device,
        load_miot_spec('cnhdm.airrtc.wkq01.json'),
        [{'props': ['prop.2.10']}, {'props': ['prop.2.8']}],
        {'hvac_mode': 'heat'},
    )


async def test_the_state_stays_in_celsius_on_a_metric_system(hass, make_device, load_miot_spec):
    hass.config.units = METRIC_SYSTEM
    entity = _thermostat(make_device, load_miot_spec)
    entity.hass = hass
    entity.set_state({entity._conv_target_temp.full_name: 20})

    assert entity.native_temperature_unit == UnitOfTemperature.CELSIUS
    assert entity.native_target_temperature == 20
    assert entity.state_attributes['temperature'] == 20
    assert entity.state_attributes['temperature_unit'] == UnitOfTemperature.CELSIUS
    assert (entity.min_temp, entity.max_temp) == (5, 50)


async def test_the_base_class_converts_once_to_the_system_unit(hass, make_device, load_miot_spec):
    """The device value is handed over untouched; Home Assistant converts it."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entity = _thermostat(make_device, load_miot_spec)
    entity.hass = hass
    entity.set_state({entity._conv_target_temp.full_name: 20})

    assert entity.native_target_temperature == 20
    assert entity.state_attributes['temperature'] == 68
    assert entity.state_attributes['temperature_unit'] == UnitOfTemperature.FAHRENHEIT
    capabilities = entity.capability_attributes
    assert (capabilities['min_temp'], capabilities['max_temp']) == (41, 122)


def test_the_water_heater_bounds_come_from_the_native_range():
    """`min_temp`/`max_temp` read the native range bounds, without going through
    the deprecated names."""
    class Standalone:
        """Borrowing the properties keeps the device machinery out of it."""

        _prop_target_temp = SimpleNamespace(range_min=lambda: 35, range_max=lambda: 75)
        native_target_temperature_low = water_heater.MiotWaterHeaterEntity.native_target_temperature_low
        native_target_temperature_high = water_heater.MiotWaterHeaterEntity.native_target_temperature_high
        min_temp = water_heater.MiotWaterHeaterEntity.min_temp
        max_temp = water_heater.MiotWaterHeaterEntity.max_temp

    heater = Standalone()
    assert (heater.min_temp, heater.max_temp) == (35, 75)

    heater._prop_target_temp = None
    assert (heater.min_temp, heater.max_temp) == (water_heater.DEFAULT_MIN_TEMP, water_heater.DEFAULT_MAX_TEMP)


async def _bound_thermostat(hass, make_device, load_miot_spec, units, state, unit):
    """A thermostat whose current temperature comes from `sensor.room`."""
    from custom_components.xiaomi_miot.core.const import DATA_CUSTOMIZE

    hass.config.units = units
    entity = _thermostat(make_device, load_miot_spec)
    entity.hass = hass
    entity.entity_id = 'climate.test_thermostat'
    hass.data[DATA_CUSTOMIZE][entity.entity_id] = {'bind_sensor': 'sensor.room'}
    hass.states.async_set('sensor.room', state, {
        'device_class': 'temperature',
        'unit_of_measurement': unit,
    })
    entity.update_bind_sensor()
    return entity


async def test_a_bound_sensor_is_converted_once(hass, make_device, load_miot_spec):
    """The bound reading is converted to the entity's unit and Home Assistant
    converts that to the system unit. Converting it to the system unit here, as
    before, made a 20 °C room read 154.4 °F on a °C device."""
    entity = await _bound_thermostat(
        hass, make_device, load_miot_spec, US_CUSTOMARY_SYSTEM, '20', UnitOfTemperature.CELSIUS,
    )
    assert entity.native_current_temperature == 20
    assert entity.state_attributes['current_temperature'] == 68


async def test_a_bound_sensor_in_another_unit_lands_in_the_native_unit(hass, make_device, load_miot_spec):
    entity = await _bound_thermostat(
        hass, make_device, load_miot_spec, METRIC_SYSTEM, '68', UnitOfTemperature.FAHRENHEIT,
    )
    assert entity.native_current_temperature == 20
    assert entity.state_attributes['current_temperature'] == 20
