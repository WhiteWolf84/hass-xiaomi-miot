"""Regression tests for the device registry listener.

The listener resolves a registry event to the Xiaomi Miot device it belongs to.
It must find it through the device's own config entry and ignore devices of
other domains, unknown or removed ids and child devices, as it did before the
single config entry rework of the device registry.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_miot import DOMAIN, _handle_device_registry_event
from custom_components.xiaomi_miot.core.hass_entry import HassEntry

IDENTIFIERS = {(DOMAIN, "14:d8:81:9c:f5:9c")}


@pytest.fixture
async def listener(hass):
    """Return the registered listener, called directly so its errors surface."""
    with patch.object(type(hass.bus), "async_listen", autospec=True) as async_listen:
        await _handle_device_registry_event(hass)
    _, event_type, callback = async_listen.call_args.args
    assert event_type == dr.EVENT_DEVICE_REGISTRY_UPDATED

    async def _call(action, device_id):
        await callback(SimpleNamespace(data={"action": action, "device_id": device_id}))

    return _call


@pytest.fixture
def miot_device(hass):
    """A loaded Xiaomi Miot entry holding one running device."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass_entry = HassEntry(hass, entry)
    entry.runtime_data = hass_entry
    device = SimpleNamespace(
        identifiers=IDENTIFIERS,
        coordinators=[object()],
        async_unload=AsyncMock(),
        init_coordinators=AsyncMock(),
        log=Mock(),
    )
    hass_entry.devices["14:d8:81:9c:f5:9c"] = device
    return SimpleNamespace(entry=entry, device=device)


async def test_own_device_is_found(hass, listener, miot_device):
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=miot_device.entry.entry_id,
        identifiers=IDENTIFIERS,
        disabled_by=dr.DeviceEntryDisabler.USER,
    )

    await listener("update", device.id)

    miot_device.device.async_unload.assert_awaited_once()


async def test_device_of_another_domain_is_ignored(hass, listener, miot_device):
    other = MockConfigEntry(domain="other_domain", data={})
    other.add_to_hass(hass)
    registry = dr.async_get(hass)
    foreign = registry.async_get_or_create(
        config_entry_id=other.entry_id,
        identifiers={("other_domain", "foreign")},
        disabled_by=dr.DeviceEntryDisabler.USER,
    )
    # Same identifiers as the Xiaomi device, but owned by another domain's entry.
    lookalike = registry.async_get_or_create(
        config_entry_id=other.entry_id,
        identifiers=IDENTIFIERS,
        disabled_by=dr.DeviceEntryDisabler.USER,
    )

    await listener("update", foreign.id)
    await listener("update", lookalike.id)

    miot_device.device.async_unload.assert_not_awaited()


async def test_unknown_and_removed_ids_are_ignored(hass, listener, miot_device):
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=miot_device.entry.entry_id,
        identifiers=IDENTIFIERS,
    )
    registry.async_remove_device(device.id)

    await listener("remove", device.id)
    await listener("update", "no-such-device")

    miot_device.device.async_unload.assert_not_awaited()
    miot_device.device.init_coordinators.assert_not_awaited()


async def test_child_device_is_ignored(hass, listener, miot_device):
    registry = dr.async_get(hass)
    parent = registry.async_get_or_create(
        config_entry_id=miot_device.entry.entry_id,
        identifiers={(DOMAIN, "gateway")},
    )
    child = registry.async_get_or_create_child(
        config_entry_id=miot_device.entry.entry_id,
        identifiers=IDENTIFIERS,
        parent_device_id=parent.id,
        disabled_by=dr.DeviceEntryDisabler.USER,
    )

    await listener("update", child.id)

    miot_device.device.async_unload.assert_not_awaited()
