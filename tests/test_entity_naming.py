"""The naming rules themselves, away from Home Assistant and from any device.

With `has_entity_name` set, Home Assistant renders "<device name> <entity
name>". Everything here exists to make sure the second half is the entity's own
contribution and never repeats the first: an entity that stands for the whole
device answers None, and one that stands for a feature answers just the feature.

Entity ids are unaffected by any of it. The converter based entities derive
theirs from model + MAC + spec description (`MiotSpec.generate_entity_id_by_mac`)
and the sub entities from the parent's `entity_id_prefix` plus the attribute
name. The display name is not an input to either -- `test_naming_by_model`
pins that down against real device specs.
"""
import pytest

from custom_components.xiaomi_miot import BaseEntity, MiotEntity
from custom_components.xiaomi_miot.core.naming import entity_own_name, spec_entity_name


class _Named(BaseEntity):
    """BaseEntity does not define device_name; the concrete classes do."""

    def __init__(self, device_name):
        self._device_name = device_name

    @property
    def device_name(self):
        return self._device_name


class _Spec:
    """Enough of a spec object to be named: only `friendly_desc` is read."""

    def __init__(self, friendly_desc):
        self.friendly_desc = friendly_desc


class _Device:
    def __init__(self, name='Deumidificatore', main_service=None):
        self.name = name
        self.main_service = main_service


def legacy_entity(name, service=None, device=None):
    """A `MiotEntity` without its constructor, which wants a live connection."""
    entity = object.__new__(MiotEntity)
    entity._name = name
    entity._miot_service = service
    entity.device = device if device is not None else _Device()
    return entity


@pytest.mark.parametrize(
    ('device_name', 'full_name', 'expected'),
    [
        # the common case: the service description is what remains
        ('Camera da letto AC', 'Camera da letto AC Air Conditioner', 'Air Conditioner'),
        # an entity carrying no name of its own -> None, so HA shows the device name
        ('Camera da letto AC', 'Camera da letto AC', None),
        # sub entity: parent name plus attribute
        ('Deumidificatore', 'Deumidificatore Relative Humidity', 'Relative Humidity'),
        # prefix match is case insensitive
        ('SALOTTO Fan', 'salotto fan Fan Level', 'Fan Level'),
        # a name that does not start with the device name is left alone
        ('Deumidificatore', 'Environment Temperature', 'Environment Temperature'),
        # surrounding whitespace never leaks into the result
        ('Deumidificatore', '  Deumidificatore   Device Fault  ', 'Device Fault'),
        # a device name longer than the entity name cannot be a prefix of it
        ('Fan Level', 'Fan', 'Fan'),
        # no device name to compare against
        (None, 'Fan Level', 'Fan Level'),
    ],
)
def test_device_prefix_is_stripped(device_name, full_name, expected):
    assert entity_own_name(full_name, device_name) == expected


@pytest.mark.parametrize('empty', ['', '   ', None])
def test_empty_name_becomes_none(empty):
    assert entity_own_name(empty, 'Deumidificatore') is None


def test_partial_word_match_is_not_stripped():
    """Only a whole word counts, not a device name that merely looks similar."""
    assert entity_own_name('Fantasy Mode', 'Fan') == 'Fantasy Mode'


def test_a_separator_is_enough_of_a_boundary():
    """The device name need not be followed by a space to be a real prefix."""
    assert entity_own_name('Fan - Level', 'Fan') == '- Level'


def test_legacy_hierarchy_shares_the_rule():
    assert _Named('Deumidificatore').entity_name_without_device(
        'Deumidificatore Relative Humidity'
    ) == 'Relative Humidity'


def test_missing_device_name_leaves_the_name_untouched():
    """BaseEntity has no device_name; the helper must not fail on it."""
    assert BaseEntity().entity_name_without_device('Environment Temperature') == (
        'Environment Temperature'
    )


def test_has_entity_name_is_enabled_on_the_legacy_hierarchy():
    """Assert on an instance, not on the class.

    Home Assistant rewrites class level `_attr_*` assignments into properties
    backed by a private slot, so reading the attribute off the class returns
    that property object rather than the value.
    """
    assert BaseEntity().has_entity_name is True


def test_the_main_service_has_no_name_of_its_own():
    main = _Spec('Dehumidifier')
    assert spec_entity_name('Camera', main_service=main, service=main) is None


def test_another_service_keeps_its_description():
    main = _Spec('Dehumidifier')
    other = _Spec('Indicator Light')
    assert spec_entity_name('Camera', main_service=main, service=other) == 'Indicator Light'


def test_a_property_of_the_main_service_is_still_a_feature():
    """`Device Fault` on a dehumidifier names a feature, not the device."""
    main = _Spec('Dehumidifier')
    fault = _Spec('Device Fault')
    assert spec_entity_name(
        'Camera', main_service=main, service=main, prop=fault,
    ) == 'Device Fault'


def test_an_action_is_named_after_itself():
    assert spec_entity_name('Camera', action=_Spec('Reset Filter')) == 'Reset Filter'


def test_nothing_to_name_after_is_nothing_to_say():
    assert spec_entity_name('Camera') is None


def test_a_device_without_a_main_service_names_every_service():
    """No main service means no entity may claim to be the device."""
    service = _Spec('Left Switch Service')
    assert spec_entity_name('Ingresso', service=service) == 'Left Switch Service'


def test_legacy_main_entity_has_no_name():
    service = object()
    entity = legacy_entity(
        'Salotto Robot Cleaner',
        service=service,
        device=_Device('Salotto', main_service=service),
    )
    assert entity.name is None


def test_legacy_secondary_entity_keeps_its_service_description():
    entity = legacy_entity(
        'Salotto Robot Cleaner',
        service=object(),
        device=_Device('Salotto', main_service=object()),
    )
    assert entity.name == 'Robot Cleaner'


def test_legacy_entity_without_a_service_is_named_as_before():
    entity = legacy_entity('Salotto Water Heater', device=_Device('Salotto'))
    assert entity.name == 'Water Heater'


def test_sub_entities_of_a_main_entity_survive_the_round_trip():
    """`BaseSubEntity` builds "<parent name or device name> <attr>".

    A main entity answers None, so the device name stands in; reading the
    result back must leave the attribute alone rather than a stray "None".
    """
    service = object()
    parent = legacy_entity(
        'Salotto Robot Cleaner',
        service=service,
        device=_Device('Salotto', main_service=service),
    )
    composed = f'{parent.name or parent.device_name} Fault'
    assert composed == 'Salotto Fault'
    assert entity_own_name(composed, parent.device_name) == 'Fault'
