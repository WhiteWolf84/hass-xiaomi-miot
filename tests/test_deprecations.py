"""Home Assistant APIs this integration used to rely on, and the way out of them.

Two deprecations show up in the Home Assistant log at startup:

  * the `CONCENTRATION_*` constants, gone in HA 2027.8, whose replacements
    (`UnitOfDensity`, `UnitOfRatio`) do not exist yet on our declared floor of
    HA 2026.1.0 — so the unit literals live here instead;
  * `TrackerEntity.location_name` and `BaseTrackerEntity.battery_level`, which
    stop being supported in HA 2027.7 and may not be overridden.

Both warnings are emitted at import or subclass creation time, so the checks
below are on the module and the class, not on a running entity.
"""
import ast
import inspect

import homeassistant.const as ha_const

from custom_components.xiaomi_miot.core import miot_spec
from custom_components.xiaomi_miot import device_tracker
from custom_components.xiaomi_miot.device_tracker import MiotTrackerEntity


def _source(module):
    with open(inspect.getsourcefile(module), encoding='utf-8') as file:
        return file.read()


# --- concentration units -----------------------------------------------------

def test_the_deprecated_constants_are_no_longer_imported():
    """Importing them is what makes Home Assistant log the warning, so it is the
    import statements that have to be clean — the comment explaining why may
    well keep naming them."""
    imported = {
        alias.name
        for node in ast.walk(ast.parse(_source(miot_spec)))
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert not [name for name in imported if name.startswith('CONCENTRATION_')]


def test_the_literals_still_match_home_assistant():
    """Our own constants have to stay byte identical to the ones HA ships,
    otherwise recorded statistics break on an existing installation."""
    assert miot_spec.MICROGRAMS_PER_CUBIC_METER == ha_const.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
    assert miot_spec.MILLIGRAMS_PER_CUBIC_METER == ha_const.CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER
    assert miot_spec.PARTS_PER_CUBIC_METER == ha_const.CONCENTRATION_PARTS_PER_CUBIC_METER
    assert miot_spec.PARTS_PER_MILLION == ha_const.CONCENTRATION_PARTS_PER_MILLION


def test_the_literals_match_the_replacement_units_when_available():
    """On Home Assistant versions new enough to ship them."""
    try:
        from homeassistant.const import UnitOfDensity, UnitOfRatio
    except ImportError:
        return
    assert miot_spec.MICROGRAMS_PER_CUBIC_METER == UnitOfDensity.MICROGRAMS_PER_CUBIC_METER
    assert miot_spec.MILLIGRAMS_PER_CUBIC_METER == UnitOfDensity.MILLIGRAMS_PER_CUBIC_METER
    assert miot_spec.PARTS_PER_MILLION == UnitOfRatio.PARTS_PER_MILLION


# --- device tracker ----------------------------------------------------------

def test_the_tracker_does_not_override_the_deprecated_properties():
    """`__init_subclass__` warns on the presence of either name in the class
    body, so it is the class dict that has to stay clean, on every subclass."""
    for cls in (MiotTrackerEntity, *MiotTrackerEntity.__subclasses__()):
        assert 'location_name' not in cls.__dict__, cls.__name__
        assert 'battery_level' not in cls.__dict__, cls.__name__


def test_the_tracker_never_sets_the_deprecated_attribute():
    """Assigning `_attr_location_name` warns too, once per instance."""
    assert '_attr_location_name' not in _source(device_tracker)


def test_the_battery_lookup_survived_as_a_plain_helper():
    """The value is still read from the device, it just travels as an
    attribute now instead of through the deprecated property."""
    class Standalone:
        """Borrowing the method keeps Home Assistant's entity machinery out of it."""

        _miot_service = None
        get_battery_level = MiotTrackerEntity.get_battery_level

    assert Standalone().get_battery_level() is None
