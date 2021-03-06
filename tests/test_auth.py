import json
import pytest

import base64

from libtaxii.constants import ST_UNAUTHORIZED, ST_BAD_MESSAGE
from opentaxii.taxii.http import HTTP_AUTHORIZATION

from utils import prepare_headers, is_headers_valid, as_tm

INBOX = dict(
    id='inbox-A',
    type='inbox',
    description='inboxA description',
    address='/path/inbox',
    authentication_required=True
)

DISCOVERY = dict(
    id='discovery-A',
    type='discovery',
    description='discoveryA description',
    address='/path/discovery',
    advertised_services=['inboxA', 'discoveryA'],
    protocol_bindings=['urn:taxii.mitre.org:protocol:http:1.0'],
    authentication_required=True,
)

SERVICES = [INBOX, DISCOVERY]

MESSAGE_ID = '123'

USERNAME = 'some-username'
PASSWORD = 'some-password'

AUTH_PATH = '/management/auth'


@pytest.fixture(autouse=True)
def prepare_server(server):
    server.persistence.create_services_from_object(SERVICES)
    server.auth.create_account(USERNAME, PASSWORD)


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_unauthorized_request(server, client, version, https):

    base_url = '%s://localhost' % ('https' if https else 'http')

    response = client.post(
        INBOX['address'],
        data='invalid-body',
        headers=prepare_headers(version, https),
        base_url=base_url
    )

    assert response.status_code == 200
    assert is_headers_valid(response.headers, version, https)

    message = as_tm(version).get_message_from_xml(response.data)
    assert message.status_type == ST_UNAUTHORIZED

    from opentaxii import context
    assert not hasattr(context, 'account')


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_get_token(client, version, https):

    base_url = '%s://localhost' % ('https' if https else 'http')

    # Invalid credentials
    response = client.post(
        AUTH_PATH,
        data={'username': 'dummy', 'password': 'wrong'},
        base_url=base_url
    )
    assert response.status_code == 401

    # Invalid auth data
    response = client.post(
        AUTH_PATH,
        data={'other': 'somethind'},
        base_url=base_url
    )
    assert response.status_code == 400

    # Valid credentials as form data
    response = client.post(
        AUTH_PATH,
        data={'username': USERNAME, 'password': PASSWORD},
        base_url=base_url
    )

    assert response.status_code == 200

    data = json.loads(response.get_data(as_text=True))
    assert data.get('token')

    # Valid credentials as JSON blob
    response = client.post(
        AUTH_PATH,
        data=json.dumps({'username': USERNAME, 'password': PASSWORD}),
        base_url=base_url,
        content_type='application/json'
    )

    assert response.status_code == 200

    data = json.loads(response.get_data(as_text=True))
    assert data.get('token')


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_get_token_and_send_request(client, version, https):

    base_url = '%s://localhost' % ('https' if https else 'http')

    # Get valid token
    response = client.post(
        AUTH_PATH,
        data={'username': USERNAME, 'password': PASSWORD},
        base_url=base_url
    )

    assert response.status_code == 200

    data = json.loads(response.get_data(as_text=True))
    token = data.get('token')

    assert token

    headers = prepare_headers(version, https)
    headers[HTTP_AUTHORIZATION] = 'Bearer %s' % token

    # Get correct response for invalid body
    response = client.post(
        INBOX['address'],
        data='invalid-body',
        headers=headers,
        base_url=base_url
    )

    assert response.status_code == 200
    assert is_headers_valid(response.headers, version, https)

    message = as_tm(version).get_message_from_xml(response.data)
    assert message.status_type == ST_BAD_MESSAGE

    request = as_tm(version).DiscoveryRequest(message_id=MESSAGE_ID)
    headers = prepare_headers(version, https)
    headers[HTTP_AUTHORIZATION] = 'Bearer %s' % token

    # Get correct response for valid request
    response = client.post(
        DISCOVERY['address'],
        data=request.to_xml(),
        headers=headers,
        base_url=base_url
    )

    assert response.status_code == 200
    assert is_headers_valid(response.headers, version=version, https=https)

    message = as_tm(version).get_message_from_xml(response.data)

    assert isinstance(message, as_tm(version).DiscoveryResponse)

    from opentaxii import context
    assert not hasattr(context, 'account')


def basic_auth_token(username, password):
    return base64.b64encode(
        '{}:{}'.format(username, password).encode('utf-8'))


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_request_with_basic_auth(client, version, https):

    base_url = '%s://localhost' % ('https' if https else 'http')
    basic_auth_header = 'Basic {}'.format(
        basic_auth_token(USERNAME, PASSWORD).decode('utf-8'))

    headers = prepare_headers(version, https)
    headers[HTTP_AUTHORIZATION] = basic_auth_header

    # Get correct response for invalid body
    response = client.post(
        INBOX['address'],
        data='invalid-body',
        headers=headers,
        base_url=base_url
    )

    assert response.status_code == 200
    assert is_headers_valid(response.headers, version, https)

    message = as_tm(version).get_message_from_xml(response.data)
    assert message.status_type == ST_BAD_MESSAGE

    request = as_tm(version).DiscoveryRequest(message_id=MESSAGE_ID)
    headers = prepare_headers(version, https)
    headers[HTTP_AUTHORIZATION] = basic_auth_header

    # Get correct response for valid request
    response = client.post(
        DISCOVERY['address'],
        data=request.to_xml(),
        headers=headers,
        base_url=base_url
    )

    assert response.status_code == 200
    assert is_headers_valid(response.headers, version=version, https=https)

    message = as_tm(version).get_message_from_xml(response.data)

    assert isinstance(message, as_tm(version).DiscoveryResponse)

    from opentaxii import context
    assert not hasattr(context, 'account')


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_invalid_basic_auth_request(client, version, https):

    base_url = '%s://localhost' % ('https' if https else 'http')

    headers = prepare_headers(version, https)
    headers[HTTP_AUTHORIZATION] = 'Basic somevalue'

    request = as_tm(version).DiscoveryRequest(message_id=MESSAGE_ID)
    response = client.post(
        DISCOVERY['address'],
        data=request.to_xml(),
        headers=headers,
        base_url=base_url
    )

    assert response.status_code == 200
    assert is_headers_valid(response.headers, version, https)

    message = as_tm(version).get_message_from_xml(response.data)
    assert message.status_type == ST_UNAUTHORIZED


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_invalid_auth_header_request(client, version, https):

    base_url = '%s://localhost' % ('https' if https else 'http')

    headers = prepare_headers(version, https)

    basic_auth_header = 'Foo {}'.format(basic_auth_token(USERNAME, PASSWORD))
    headers[HTTP_AUTHORIZATION] = basic_auth_header

    request = as_tm(version).DiscoveryRequest(message_id=MESSAGE_ID)
    response = client.post(
        DISCOVERY['address'],
        data=request.to_xml(),
        headers=headers,
        base_url=base_url
    )

    assert response.status_code == 200
    assert is_headers_valid(response.headers, version, https)

    message = as_tm(version).get_message_from_xml(response.data)
    assert message.status_type == ST_UNAUTHORIZED
