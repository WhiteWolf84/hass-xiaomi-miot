"""Naming behaviour of the legacy entity hierarchy under has_entity_name.

These entities build `_name` as "<device name> <service description>". Home
Assistant composes that same pairing itself once `has_entity_name` is set, so
the entity must expose only its own half or the device name renders twice.

Entity ids are unaffected by any of this: the main entities derive theirs from
model + MAC + service desc_name (`MiotSpec.generate_entity_id_by_mac`) and the
sub entities from the parent's `entity_id_prefix` plus the attribute name. The
display name is not an input to either.
"""
from types import SimpleNamespace

import pytest

from custom_components.xiaomi_miot import BaseEntity


class _Named(BaseEntity):
    """BaseEntity does not define device_name; the concrete classes do."""

    def __init__(self, device_name):
        self._device_name = device_name

    @property
    def device_name(self):
        return self._device_name


def test_has_entity_name_is_enabled_on_the_legacy_hierarchy():
    """Assert on an instance, not on the class.

    Home Assistant rewrites class level `_attr_*` assignments into properties
    backed by a private slot, so reading the attribute off the class returns
    that property object rather than the value.
    """
    assert BaseEntity().has_entity_name is True


@pytest.mark.parametrize(
    ('device_name', 'full_name', 'expected'),
    [
        # the common case: the service description is what remains
        ('Camera da letto AC', 'Camera da letto AC Air Conditioner', 'Air Conditioner'),
        # main entity carrying no name of its own -> None, so HA shows the device name
        ('Camera da letto AC', 'Camera da letto AC', None),
        # sub entity: parent name plus attribute
        ('Deumidificatore', 'Deumidificatore Relative Humidity', 'Relative Humidity'),
        # prefix match is case insensitive
        ('SALOTTO Fan', 'salotto fan Fan Level', 'Fan Level'),
        # a name that does not start with the device name is left alone
        ('Deumidificatore', 'Environment Temperature', 'Environment Temperature'),
        # surrounding whitespace never leaks into the result
        ('Deumidificatore', '  Deumidificatore   Device Fault  ', 'Device Fault'),
    ],
)
def test_device_prefix_is_stripped(device_name, full_name, expected):
    assert _Named(device_name).entity_name_without_device(full_name) == expected


@pytest.mark.parametrize('empty', ['', '   ', None])
def test_empty_name_becomes_none(empty):
    assert _Named('Deumidificatore').entity_name_without_device(empty) is None


def test_missing_device_name_leaves_the_name_untouched():
    """BaseEntity has no device_name; the helper must not fail on it."""
    ent = BaseEntity()
    assert ent.entity_name_without_device('Environment Temperature') == 'Environment Temperature'


def test_partial_word_match_is_not_stripped():
    """Only a real prefix counts, not a device name that merely looks similar."""
    assert _Named('Fan').entity_name_without_device('Fantasy Mode') == 'tasy Mode'
