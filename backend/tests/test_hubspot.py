# backend/tests/test_hubspot.py
import json
import base64
import pytest
from unittest.mock import patch, AsyncMock

from integrations import hubspot


@pytest.mark.asyncio
async def test_authorize_hubspot_returns_url_with_state_and_writes_to_redis():
    captured = {}

    async def fake_add(key, value, expire=None):
        captured[key] = value

    with patch.object(hubspot, "add_key_value_redis", AsyncMock(side_effect=fake_add)):
        url = await hubspot.authorize_hubspot("user-1", "org-1")

    assert url.startswith("https://app.hubspot.com/oauth/authorize")
    assert f"client_id={hubspot.CLIENT_ID}" in url
    assert "state=" in url
    redis_key = "hubspot_state:org-1:user-1"
    assert redis_key in captured
    state_data = json.loads(captured[redis_key])
    assert state_data["user_id"] == "user-1"
    assert state_data["org_id"] == "org-1"
    assert "state" in state_data


@pytest.mark.asyncio
async def test_oauth2callback_hubspot_exchanges_code_and_stores_credentials():
    state_data = {'state': 'abc', 'user_id': 'user-1', 'org_id': 'org-1'}
    encoded_state = base64.urlsafe_b64encode(
        json.dumps(state_data).encode('utf-8')
    ).decode('utf-8')

    class FakeRequest:
        query_params = {'code': 'auth-code', 'state': encoded_state}

    saved = {f'hubspot_state:org-1:user-1': json.dumps(state_data).encode()}

    async def fake_get(key):
        return saved.get(key)

    async def fake_add(key, value, expire=None):
        saved[key] = value.encode() if isinstance(value, str) else value

    async def fake_delete(key):
        saved.pop(key, None)

    class FakeResponse:
        def json(self):
            return {'access_token': 'tok', 'refresh_token': 'r', 'expires_in': 1800}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, data=None, headers=None):
            assert url == hubspot.TOKEN_URL
            assert data['grant_type'] == 'authorization_code'
            assert data['code'] == 'auth-code'
            assert data['client_id'] == hubspot.CLIENT_ID
            assert data['client_secret'] == hubspot.CLIENT_SECRET
            assert data['redirect_uri'] == hubspot.REDIRECT_URI
            return FakeResponse()

    with patch.object(hubspot, 'get_value_redis', AsyncMock(side_effect=fake_get)), \
         patch.object(hubspot, 'add_key_value_redis', AsyncMock(side_effect=fake_add)), \
         patch.object(hubspot, 'delete_key_redis', AsyncMock(side_effect=fake_delete)), \
         patch.object(hubspot.httpx, 'AsyncClient', lambda: FakeClient()):
        result = await hubspot.oauth2callback_hubspot(FakeRequest())

    assert result.status_code == 200
    creds = json.loads(saved['hubspot_credentials:org-1:user-1'])
    assert creds['access_token'] == 'tok'


@pytest.mark.asyncio
async def test_get_hubspot_credentials_returns_and_deletes():
    saved = {'hubspot_credentials:org-1:user-1': json.dumps({'access_token': 'tok'}).encode()}

    async def fake_get(key):
        return saved.get(key)

    async def fake_delete(key):
        saved.pop(key, None)

    with patch.object(hubspot, 'get_value_redis', AsyncMock(side_effect=fake_get)), \
         patch.object(hubspot, 'delete_key_redis', AsyncMock(side_effect=fake_delete)):
        creds = await hubspot.get_hubspot_credentials('user-1', 'org-1')

    assert creds == {'access_token': 'tok'}
    assert 'hubspot_credentials:org-1:user-1' not in saved


@pytest.mark.asyncio
async def test_get_hubspot_credentials_raises_when_missing():
    with patch.object(hubspot, 'get_value_redis', AsyncMock(return_value=None)):
        with pytest.raises(Exception):
            await hubspot.get_hubspot_credentials('user-1', 'org-1')


def test_create_integration_item_metadata_object_for_contact():
    sample = {
        'id': '101',
        'createdAt': '2024-01-02T03:04:05Z',
        'updatedAt': '2024-02-03T04:05:06Z',
        'properties': {
            'firstname': 'Ada',
            'lastname': 'Lovelace',
            'email': 'ada@example.com',
        },
    }
    item = hubspot.create_integration_item_metadata_object(sample, 'contact')
    assert item.id == '101_contact'
    assert item.type == 'contact'
    assert item.name == 'Ada Lovelace'
    assert item.creation_time == '2024-01-02T03:04:05Z'
    assert item.last_modified_time == '2024-02-03T04:05:06Z'
    assert item.url == 'https://app.hubspot.com/contacts/_/contact/101'


def test_create_integration_item_metadata_object_for_company_falls_back_to_id():
    sample = {'id': '202', 'properties': {}, 'createdAt': None, 'updatedAt': None}
    item = hubspot.create_integration_item_metadata_object(sample, 'company')
    assert item.id == '202_company'
    assert item.type == 'company'
    assert item.name == 'company 202'


def test_get_items_hubspot_aggregates_objects(monkeypatch):
    payloads = {
        'https://api.hubapi.com/crm/v3/objects/contacts': {
            'results': [
                {'id': '1', 'properties': {'firstname': 'Ada', 'lastname': 'L'},
                 'createdAt': 'a', 'updatedAt': 'b'},
            ]
        },
        'https://api.hubapi.com/crm/v3/objects/companies': {
            'results': [
                {'id': '2', 'properties': {'name': 'Acme'},
                 'createdAt': 'a', 'updatedAt': 'b'},
            ]
        },
        'https://api.hubapi.com/crm/v3/objects/deals': {
            'results': [
                {'id': '3', 'properties': {'dealname': 'Big Deal'},
                 'createdAt': 'a', 'updatedAt': 'b'},
            ]
        },
    }

    class FakeResp:
        status_code = 200

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    def fake_get(url, headers=None, params=None):
        base = url.split('?')[0]
        return FakeResp(payloads[base])

    monkeypatch.setattr(hubspot.requests, 'get', fake_get)

    items = hubspot.get_items_hubspot(json.dumps({'access_token': 'tok'}))
    assert len(items) == 3
    assert {i.type for i in items} == {'contact', 'company', 'deal'}
