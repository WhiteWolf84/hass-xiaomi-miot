"""The config and options flow steps every user walks through.

The reauth branch is covered by test_reauth_flow.py and the cloud steps by the
test_cloud_auth_* modules; this covers the entry points and the routing between
them, which had no tests at all.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_miot import DOMAIN, init_integration_data
from custom_components.xiaomi_miot.config_flow import (
    BaseFlowHandler,
    OptionsFlowHandler,
    XiaomiMiotFlowHandler,
)


def _flow(hass):
    flow = XiaomiMiotFlowHandler()
    flow.hass = hass
    flow.context = {}
    return flow


# --- BaseFlowHandler ---------------------------------------------------------

def test_placeholders_are_created_on_first_access():
    base = BaseFlowHandler()
    base.context = {}
    base.placeholders['tip'] = 'ciao'
    assert base.context['placeholders'] == {'tip': 'ciao'}


def test_pop_placeholders_always_supplies_tip():
    base = BaseFlowHandler()
    base.context = {}
    assert base.pop_placeholders() == {'tip': ''}


def test_pop_placeholders_clears_the_context():
    base = BaseFlowHandler()
    base.context = {'placeholders': {'tip': 'x', 'verify_url': 'u'}}
    assert base.pop_placeholders() == {'tip': 'x', 'verify_url': 'u'}
    assert 'placeholders' not in base.context


# --- async_step_user ---------------------------------------------------------

async def test_user_step_shows_the_action_form(hass):
    flow = _flow(hass)
    init_integration_data(hass)

    result = await flow.async_step_user()

    assert result['type'] == 'form'
    assert result['step_id'] == 'user'
    schema = result['data_schema'].schema
    actions = next(v for k, v in schema.items() if str(k) == 'action')
    assert set(actions.container) == {'account', 'token'}


async def test_customizing_actions_appear_only_with_entities(hass):
    """The customizing choices are pointless before any entity exists."""
    flow = _flow(hass)
    init_integration_data(hass)
    hass.data[DOMAIN]['entities']['sensor.whatever'] = object()

    result = await flow.async_step_user()

    actions = next(
        v for k, v in result['data_schema'].schema.items() if str(k) == 'action'
    )
    assert set(actions.container) == {
        'account', 'token', 'customizing_device', 'customizing_entity',
    }


@pytest.mark.parametrize('action', ['account', 'cloud'])
async def test_account_actions_route_to_the_cloud_step(hass, action):
    flow = _flow(hass)
    init_integration_data(hass)
    flow.async_step_cloud = AsyncMock(return_value={'type': 'form', 'step_id': 'cloud'})

    result = await flow.async_step_user({'action': action})

    flow.async_step_cloud.assert_awaited_once()
    assert result['step_id'] == 'cloud'


@pytest.mark.parametrize(
    'action', ['customizing_entity', 'customizing_device'],
)
async def test_customizing_actions_record_how_they_were_reached(hass, action):
    flow = _flow(hass)
    init_integration_data(hass)
    flow.async_step_customizing = AsyncMock(return_value={'type': 'form'})

    await flow.async_step_user({'action': action})

    assert flow.context['customizing_via'] == action
    flow.async_step_customizing.assert_awaited_once()


async def test_unknown_action_falls_back_to_the_token_step(hass):
    flow = _flow(hass)
    init_integration_data(hass)
    flow.async_step_token = AsyncMock(return_value={'type': 'form', 'step_id': 'token'})

    result = await flow.async_step_user({'action': 'token'})

    assert result['step_id'] == 'token'


async def test_cloud_action_is_remembered_as_account(hass):
    """'cloud' is an alias for 'account' and must not leak into the form."""
    flow = _flow(hass)
    init_integration_data(hass)

    result = await flow.async_step_user()

    default = next(
        k for k in result['data_schema'].schema if str(k) == 'action'
    ).default()
    assert default == 'account'


# --- OptionsFlowHandler ------------------------------------------------------

def _options(hass, data, options=None):
    """OptionsFlow.config_entry is read-only from HA 2024.12 on: it resolves
    through hass.config_entries using `handler`, so the entry has to be really
    registered rather than stood in for."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=dict(data), options=dict(options or {}),
    )
    entry.add_to_hass(hass)
    handler = OptionsFlowHandler(entry)
    handler.hass = hass
    handler.context = {}
    handler.handler = entry.entry_id
    return handler


async def test_options_init_routes_cloud_entries_to_the_cloud_step(hass):
    handler = _options(hass, {'username': 'u'})
    handler.async_step_cloud = AsyncMock(return_value={'type': 'form', 'step_id': 'cloud'})

    result = await handler.async_step_init()

    handler.async_step_cloud.assert_awaited_once()
    assert result['step_id'] == 'cloud'


@pytest.mark.parametrize('key', ['customizing_entity', 'customizing_device'])
async def test_options_init_shows_customizes_and_aborts(hass, key):
    """A customizing entry has nothing to reconfigure; it just displays itself."""
    handler = _options(hass, {key: {'sensor.x': {'state_class': 'measurement'}}})
    handler.async_abort = MagicMock(return_value={'type': 'abort', 'reason': 'show_customizes'})

    result = await handler.async_step_init()

    assert result['reason'] == 'show_customizes'
    placeholders = handler.async_abort.call_args.kwargs['description_placeholders']
    assert 'state_class' in placeholders['tip']
    assert 'config_flow_start' in placeholders['link']


async def test_options_init_falls_back_to_the_user_step(hass):
    """A host/token entry is reconfigured through the plain user step."""
    handler = _options(hass, {'host': '192.168.1.2', 'token': 'x' * 32})
    handler.async_step_user = AsyncMock(return_value={'type': 'form', 'step_id': 'user'})

    result = await handler.async_step_init()

    handler.async_step_user.assert_awaited_once()
    assert result['step_id'] == 'user'


def test_saved_config_merges_options_over_data(hass):
    handler = _options(
        hass,
        {'username': 'u', 'server_country': 'cn'},
        {'server_country': 'de'},
    )
    saved = handler.saved_config
    assert saved['username'] == 'u'
    assert saved['server_country'] == 'de', 'options must win over the original data'


def test_options_flow_is_offered_for_an_entry():
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    assert isinstance(
        XiaomiMiotFlowHandler.async_get_options_flow(entry), OptionsFlowHandler,
    )
