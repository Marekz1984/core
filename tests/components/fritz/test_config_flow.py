"""Tests for AVM Fritz!Box config flow."""
from unittest.mock import patch

from fritzconnection.core.exceptions import FritzConnectionException, FritzSecurityError
import pytest

from homeassistant.components.device_tracker.const import (
    CONF_CONSIDER_HOME,
    DEFAULT_CONSIDER_HOME,
)
from homeassistant.components.fritz.const import (
    DOMAIN,
    ERROR_AUTH_INVALID,
    ERROR_CANNOT_CONNECT,
    ERROR_UNKNOWN,
)
from homeassistant.components.ssdp import (
    ATTR_SSDP_LOCATION,
    ATTR_UPNP_FRIENDLY_NAME,
    ATTR_UPNP_UDN,
)
from homeassistant.config_entries import (
    SOURCE_IMPORT,
    SOURCE_REAUTH,
    SOURCE_SSDP,
    SOURCE_USER,
)
from homeassistant.const import CONF_DEVICES, CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import (
    RESULT_TYPE_ABORT,
    RESULT_TYPE_CREATE_ENTRY,
    RESULT_TYPE_FORM,
)

from . import MOCK_CONFIG, FritzConnectionMock

from tests.common import MockConfigEntry

ATTR_HOST = "host"
ATTR_NEW_SERIAL_NUMBER = "NewSerialNumber"

MOCK_HOST = "fake_host"
MOCK_SERIAL_NUMBER = "fake_serial_number"
MOCK_FIRMWARE_INFO = [True, "1.1.1"]

MOCK_USER_DATA = MOCK_CONFIG[DOMAIN][CONF_DEVICES][0]
MOCK_DEVICE_INFO = {
    ATTR_HOST: MOCK_HOST,
    ATTR_NEW_SERIAL_NUMBER: MOCK_SERIAL_NUMBER,
}
MOCK_IMPORT_CONFIG = {CONF_HOST: MOCK_HOST, CONF_USERNAME: "username"}
MOCK_SSDP_DATA = {
    ATTR_SSDP_LOCATION: "https://fake_host:12345/test",
    ATTR_UPNP_FRIENDLY_NAME: "fake_name",
    ATTR_UPNP_UDN: "uuid:only-a-test",
}

MOCK_REQUEST = b'<?xml version="1.0" encoding="utf-8"?><SessionInfo><SID>xxxxxxxxxxxxxxxx</SID><Challenge>xxxxxxxx</Challenge><BlockTime>0</BlockTime><Rights><Name>Dial</Name><Access>2</Access><Name>App</Name><Access>2</Access><Name>HomeAuto</Name><Access>2</Access><Name>BoxAdmin</Name><Access>2</Access><Name>Phone</Name><Access>2</Access><Name>NAS</Name><Access>2</Access></Rights><Users><User last="1">FakeFritzUser</User></Users></SessionInfo>\n'


@pytest.fixture()
def fc_class_mock():
    """Fixture that sets up a mocked FritzConnection class."""
    with patch("fritzconnection.FritzConnection", autospec=True) as result:
        result.return_value = FritzConnectionMock()
        yield result


async def test_user(hass: HomeAssistant, fc_class_mock, mock_get_source_ip):
    """Test starting a flow by user."""
    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=fc_class_mock,
    ), patch("homeassistant.components.fritz.common.FritzStatus"), patch(
        "homeassistant.components.fritz.common.FritzBoxTools._update_device_info",
        return_value=MOCK_FIRMWARE_INFO,
    ), patch(
        "homeassistant.components.fritz.async_setup_entry"
    ) as mock_setup_entry, patch(
        "requests.get"
    ) as mock_request_get, patch(
        "requests.post"
    ) as mock_request_post:

        mock_request_get.return_value.status_code = 200
        mock_request_get.return_value.content = MOCK_REQUEST
        mock_request_post.return_value.status_code = 200
        mock_request_post.return_value.text = MOCK_REQUEST

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_USER_DATA
        )
        assert result["type"] == RESULT_TYPE_CREATE_ENTRY
        assert result["data"][CONF_HOST] == "fake_host"
        assert result["data"][CONF_PASSWORD] == "fake_pass"
        assert result["data"][CONF_USERNAME] == "fake_user"
        assert (
            result["options"][CONF_CONSIDER_HOME]
            == DEFAULT_CONSIDER_HOME.total_seconds()
        )
        assert not result["result"].unique_id
        await hass.async_block_till_done()

    assert mock_setup_entry.called


async def test_user_already_configured(
    hass: HomeAssistant, fc_class_mock, mock_get_source_ip
):
    """Test starting a flow by user with an already configured device."""

    mock_config = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_DATA)
    mock_config.add_to_hass(hass)

    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=fc_class_mock,
    ), patch("homeassistant.components.fritz.common.FritzStatus"), patch(
        "homeassistant.components.fritz.common.FritzBoxTools._update_device_info",
        return_value=MOCK_FIRMWARE_INFO,
    ), patch(
        "requests.get"
    ) as mock_request_get, patch(
        "requests.post"
    ) as mock_request_post:

        mock_request_get.return_value.status_code = 200
        mock_request_get.return_value.content = MOCK_REQUEST
        mock_request_post.return_value.status_code = 200
        mock_request_post.return_value.text = MOCK_REQUEST

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_USER_DATA
        )
        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "user"
        assert result["errors"]["base"] == "already_configured"


async def test_exception_security(hass: HomeAssistant, mock_get_source_ip):
    """Test starting a flow by user with invalid credentials."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == RESULT_TYPE_FORM
    assert result["step_id"] == "user"

    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=FritzSecurityError,
    ), patch("homeassistant.components.fritz.common.FritzStatus"):

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_USER_DATA
        )

        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "user"
        assert result["errors"]["base"] == ERROR_AUTH_INVALID


async def test_exception_connection(hass: HomeAssistant, mock_get_source_ip):
    """Test starting a flow by user with a connection error."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == RESULT_TYPE_FORM
    assert result["step_id"] == "user"

    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=FritzConnectionException,
    ), patch("homeassistant.components.fritz.common.FritzStatus"):

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_USER_DATA
        )

        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "user"
        assert result["errors"]["base"] == ERROR_CANNOT_CONNECT


async def test_exception_unknown(hass: HomeAssistant, mock_get_source_ip):
    """Test starting a flow by user with an unknown exception."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == RESULT_TYPE_FORM
    assert result["step_id"] == "user"

    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=OSError,
    ), patch("homeassistant.components.fritz.common.FritzStatus"):

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_USER_DATA
        )

        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "user"
        assert result["errors"]["base"] == ERROR_UNKNOWN


async def test_reauth_successful(
    hass: HomeAssistant, fc_class_mock, mock_get_source_ip
):
    """Test starting a reauthentication flow."""

    mock_config = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_DATA)
    mock_config.add_to_hass(hass)

    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=fc_class_mock,
    ), patch("homeassistant.components.fritz.common.FritzStatus"), patch(
        "homeassistant.components.fritz.common.FritzBoxTools._update_device_info",
        return_value=MOCK_FIRMWARE_INFO,
    ), patch(
        "homeassistant.components.fritz.async_setup_entry"
    ) as mock_setup_entry, patch(
        "requests.get"
    ) as mock_request_get, patch(
        "requests.post"
    ) as mock_request_post:

        mock_request_get.return_value.status_code = 200
        mock_request_get.return_value.content = MOCK_REQUEST
        mock_request_post.return_value.status_code = 200
        mock_request_post.return_value.text = MOCK_REQUEST

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": mock_config.entry_id},
            data=mock_config.data,
        )

        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "other_fake_user",
                CONF_PASSWORD: "other_fake_password",
            },
        )

        assert result["type"] == RESULT_TYPE_ABORT
        assert result["reason"] == "reauth_successful"

    assert mock_setup_entry.called


async def test_reauth_not_successful(
    hass: HomeAssistant, fc_class_mock, mock_get_source_ip
):
    """Test starting a reauthentication flow but no connection found."""

    mock_config = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_DATA)
    mock_config.add_to_hass(hass)

    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=FritzConnectionException,
    ), patch("homeassistant.components.fritz.common.FritzStatus"):

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": mock_config.entry_id},
            data=mock_config.data,
        )

        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "other_fake_user",
                CONF_PASSWORD: "other_fake_password",
            },
        )

        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "reauth_confirm"
        assert result["errors"]["base"] == "cannot_connect"


async def test_ssdp_already_configured(
    hass: HomeAssistant, fc_class_mock, mock_get_source_ip
):
    """Test starting a flow from discovery with an already configured device."""

    mock_config = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_DATA,
        unique_id="only-a-test",
    )
    mock_config.add_to_hass(hass)

    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=fc_class_mock,
    ), patch("homeassistant.components.fritz.common.FritzStatus"):

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_SSDP}, data=MOCK_SSDP_DATA
        )
        assert result["type"] == RESULT_TYPE_ABORT
        assert result["reason"] == "already_configured"


async def test_ssdp_already_configured_host(
    hass: HomeAssistant, fc_class_mock, mock_get_source_ip
):
    """Test starting a flow from discovery with an already configured host."""

    mock_config = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_DATA,
        unique_id="different-test",
    )
    mock_config.add_to_hass(hass)

    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=fc_class_mock,
    ), patch("homeassistant.components.fritz.common.FritzStatus"):

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_SSDP}, data=MOCK_SSDP_DATA
        )
        assert result["type"] == RESULT_TYPE_ABORT
        assert result["reason"] == "already_configured"


async def test_ssdp_already_configured_host_uuid(
    hass: HomeAssistant, fc_class_mock, mock_get_source_ip
):
    """Test starting a flow from discovery with an already configured uuid."""

    mock_config = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_DATA,
        unique_id=None,
    )
    mock_config.add_to_hass(hass)

    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=fc_class_mock,
    ), patch("homeassistant.components.fritz.common.FritzStatus"):

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_SSDP}, data=MOCK_SSDP_DATA
        )
        assert result["type"] == RESULT_TYPE_ABORT
        assert result["reason"] == "already_configured"


async def test_ssdp_already_in_progress_host(
    hass: HomeAssistant, fc_class_mock, mock_get_source_ip
):
    """Test starting a flow from discovery twice."""
    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=fc_class_mock,
    ), patch("homeassistant.components.fritz.common.FritzStatus"):

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_SSDP}, data=MOCK_SSDP_DATA
        )
        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "confirm"

        MOCK_NO_UNIQUE_ID = MOCK_SSDP_DATA.copy()
        del MOCK_NO_UNIQUE_ID[ATTR_UPNP_UDN]
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_SSDP}, data=MOCK_NO_UNIQUE_ID
        )
        assert result["type"] == RESULT_TYPE_ABORT
        assert result["reason"] == "already_in_progress"


async def test_ssdp(hass: HomeAssistant, fc_class_mock, mock_get_source_ip):
    """Test starting a flow from discovery."""
    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=fc_class_mock,
    ), patch("homeassistant.components.fritz.common.FritzStatus"), patch(
        "homeassistant.components.fritz.common.FritzBoxTools._update_device_info",
        return_value=MOCK_FIRMWARE_INFO,
    ), patch(
        "homeassistant.components.fritz.async_setup_entry"
    ) as mock_setup_entry, patch(
        "requests.get"
    ) as mock_request_get, patch(
        "requests.post"
    ) as mock_request_post:

        mock_request_get.return_value.status_code = 200
        mock_request_get.return_value.content = MOCK_REQUEST
        mock_request_post.return_value.status_code = 200
        mock_request_post.return_value.text = MOCK_REQUEST

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_SSDP}, data=MOCK_SSDP_DATA
        )
        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "fake_user",
                CONF_PASSWORD: "fake_pass",
            },
        )

        assert result["type"] == RESULT_TYPE_CREATE_ENTRY
        assert result["data"][CONF_HOST] == "fake_host"
        assert result["data"][CONF_PASSWORD] == "fake_pass"
        assert result["data"][CONF_USERNAME] == "fake_user"

    assert mock_setup_entry.called


async def test_ssdp_exception(hass: HomeAssistant, mock_get_source_ip):
    """Test starting a flow from discovery but no device found."""
    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=FritzConnectionException,
    ), patch("homeassistant.components.fritz.common.FritzStatus"):

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_SSDP}, data=MOCK_SSDP_DATA
        )
        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "fake_user",
                CONF_PASSWORD: "fake_pass",
            },
        )

        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "confirm"


async def test_import(hass: HomeAssistant, fc_class_mock, mock_get_source_ip):
    """Test importing."""
    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=fc_class_mock,
    ), patch("homeassistant.components.fritz.common.FritzStatus"), patch(
        "homeassistant.components.fritz.common.FritzBoxTools._update_device_info",
        return_value=MOCK_FIRMWARE_INFO,
    ), patch(
        "homeassistant.components.fritz.async_setup_entry"
    ) as mock_setup_entry, patch(
        "requests.get"
    ) as mock_request_get, patch(
        "requests.post"
    ) as mock_request_post:

        mock_request_get.return_value.status_code = 200
        mock_request_get.return_value.content = MOCK_REQUEST
        mock_request_post.return_value.status_code = 200
        mock_request_post.return_value.text = MOCK_REQUEST

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=MOCK_IMPORT_CONFIG
        )

        assert result["type"] == RESULT_TYPE_CREATE_ENTRY
        assert result["data"][CONF_HOST] == "fake_host"
        assert result["data"][CONF_PASSWORD] is None
        assert result["data"][CONF_USERNAME] == "username"
        await hass.async_block_till_done()

    assert mock_setup_entry.called


async def test_options_flow(hass: HomeAssistant, fc_class_mock, mock_get_source_ip):
    """Test options flow."""

    mock_config = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_DATA)
    mock_config.add_to_hass(hass)

    with patch(
        "homeassistant.components.fritz.common.FritzConnection",
        side_effect=fc_class_mock,
    ), patch("homeassistant.components.fritz.common.FritzStatus"), patch(
        "homeassistant.components.fritz.common.FritzBoxTools"
    ):
        result = await hass.config_entries.options.async_init(mock_config.entry_id)
        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_init(mock_config.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONSIDER_HOME: 37,
            },
        )
        assert result["type"] == RESULT_TYPE_CREATE_ENTRY
        assert mock_config.options[CONF_CONSIDER_HOME] == 37
