# HubSpot Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a complete HubSpot OAuth2 integration (backend + frontend) that mirrors the existing Notion and Airtable integrations and exposes a list of HubSpot CRM items as `IntegrationItem` objects.

**Architecture:** Backend FastAPI handlers in `backend/integrations/hubspot.py` follow the Airtable/Notion pattern: a redis-backed `state` token, popup-based OAuth, and credentials cached in redis under `hubspot_credentials:{org_id}:{user_id}` with a short TTL. The frontend React component opens the OAuth popup, polls until the window closes, then fetches the credentials. `get_items_hubspot` queries HubSpot CRM v3 endpoints (contacts, companies, deals) and converts each result into an `IntegrationItem`.

**Tech Stack:** Python 3.11, FastAPI, httpx, `requests`, redis (asyncio), pytest + pytest-asyncio, React 18, axios, MUI.

---

## File Structure

**Backend:**
- Modify: `backend/integrations/hubspot.py` — full implementation (replaces existing stub).
- Modify: `backend/main.py:75-77` — rename HubSpot load route from `/integrations/hubspot/get_hubspot_items` to `/integrations/hubspot/load` and stop awaiting a sync function. Aligns with airtable/notion.
- Create: `backend/tests/__init__.py` — empty package marker.
- Create: `backend/tests/test_hubspot.py` — pytest unit tests for each function in `hubspot.py`.

**Frontend:**
- Create: `frontend/src/integrations/hubspot.js` — `HubspotIntegration` React component (mirrors `airtable.js` / `notion.js`).
- Delete: `frontend/src/integrations/slack.js` — leftover empty placeholder.
- Modify: `frontend/src/integration-form.js:7-14` — import `HubspotIntegration`, add `'HubSpot'` to `integrationMapping`.
- Modify: `frontend/src/data-form.js:9-12` — add `'HubSpot': 'hubspot'` to `endpointMapping`.

---

## Prerequisites

Before Task 9 (end-to-end verification) the developer must:

1. Sign up at https://developers.hubspot.com and create a **developer test account**.
2. In the developer portal, **Apps → Create app**.
3. Under **Auth**, set the redirect URL to `http://localhost:8000/integrations/hubspot/oauth2callback`.
4. Under **Auth → Scopes**, enable: `crm.objects.contacts.read`, `crm.objects.companies.read`, `crm.objects.deals.read`. (`oauth` is granted implicitly.)
5. Copy **Client ID** and **Client Secret** for use in Task 9.

Tasks 1-8 can be implemented and unit-tested without a HubSpot account.

---

### Task 1: Implement `authorize_hubspot` (backend)

**Files:**
- Modify: `backend/integrations/hubspot.py` (entire file replaced — current contents are stubs).
- Create: `backend/tests/__init__.py`.
- Create: `backend/tests/test_hubspot.py`.

This task replaces the file's stubs with module-level constants, imports, and a working `authorize_hubspot`. Subsequent tasks fill in the remaining functions.

- [ ] **Step 1: Install test deps and create the failing test**

```bash
cd backend
./venv/bin/pip install pytest pytest-asyncio
```

Create `backend/tests/__init__.py` (empty).

Create `backend/tests/test_hubspot.py`:

```python
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
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd backend
./venv/bin/python -m pytest tests/test_hubspot.py::test_authorize_hubspot_returns_url_with_state_and_writes_to_redis -v
```

Expected: FAIL — current `authorize_hubspot` is a stub returning `None`, so `url.startswith(...)` raises `AttributeError`.

- [ ] **Step 3: Replace `backend/integrations/hubspot.py` with the scaffold + `authorize_hubspot`**

```python
# hubspot.py

import json
import secrets
import asyncio
import base64
from urllib.parse import urlencode

from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
import httpx
import requests

from integrations.integration_item import IntegrationItem
from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

CLIENT_ID = 'XXX'        # Replace with your HubSpot app's Client ID before Task 9
CLIENT_SECRET = 'XXX'    # Replace with your HubSpot app's Client Secret before Task 9
REDIRECT_URI = 'http://localhost:8000/integrations/hubspot/oauth2callback'
SCOPES = 'crm.objects.contacts.read crm.objects.companies.read crm.objects.deals.read'
AUTHORIZATION_URL = 'https://app.hubspot.com/oauth/authorize'
TOKEN_URL = 'https://api.hubapi.com/oauth/v1/token'


async def authorize_hubspot(user_id, org_id):
    state_data = {
        'state': secrets.token_urlsafe(32),
        'user_id': user_id,
        'org_id': org_id,
    }
    encoded_state = base64.urlsafe_b64encode(
        json.dumps(state_data).encode('utf-8')
    ).decode('utf-8')

    await add_key_value_redis(
        f'hubspot_state:{org_id}:{user_id}',
        json.dumps(state_data),
        expire=600,
    )

    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPES,
        'state': encoded_state,
    }
    return f'{AUTHORIZATION_URL}?{urlencode(params)}'


async def oauth2callback_hubspot(request: Request):
    raise NotImplementedError  # filled in Task 2


async def get_hubspot_credentials(user_id, org_id):
    raise NotImplementedError  # filled in Task 3


def create_integration_item_metadata_object(response_json, item_type):
    raise NotImplementedError  # filled in Task 4


def get_items_hubspot(credentials):
    raise NotImplementedError  # filled in Task 5
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
cd backend
./venv/bin/python -m pytest tests/test_hubspot.py::test_authorize_hubspot_returns_url_with_state_and_writes_to_redis -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/hubspot.py backend/tests/__init__.py backend/tests/test_hubspot.py
git commit -m "feat(hubspot): scaffold module and implement authorize_hubspot"
```

---

### Task 2: Implement `oauth2callback_hubspot` (backend)

**Files:**
- Modify: `backend/integrations/hubspot.py` (replace `oauth2callback_hubspot` body).
- Modify: `backend/tests/test_hubspot.py` (append test).

- [ ] **Step 1: Append the failing test to `backend/tests/test_hubspot.py`**

```python
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
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd backend
./venv/bin/python -m pytest tests/test_hubspot.py::test_oauth2callback_hubspot_exchanges_code_and_stores_credentials -v
```

Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Replace `oauth2callback_hubspot` in `backend/integrations/hubspot.py`**

```python
async def oauth2callback_hubspot(request: Request):
    if request.query_params.get('error'):
        raise HTTPException(
            status_code=400,
            detail=request.query_params.get('error_description') or request.query_params.get('error'),
        )

    code = request.query_params.get('code')
    encoded_state = request.query_params.get('state')
    if not code or not encoded_state:
        raise HTTPException(status_code=400, detail='Missing code or state parameter.')

    state_data = json.loads(base64.urlsafe_b64decode(encoded_state).decode('utf-8'))
    original_state = state_data.get('state')
    user_id = state_data.get('user_id')
    org_id = state_data.get('org_id')

    saved_state = await get_value_redis(f'hubspot_state:{org_id}:{user_id}')
    if not saved_state or original_state != json.loads(saved_state).get('state'):
        raise HTTPException(status_code=400, detail='State does not match.')

    async with httpx.AsyncClient() as client:
        response, _ = await asyncio.gather(
            client.post(
                TOKEN_URL,
                data={
                    'grant_type': 'authorization_code',
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'redirect_uri': REDIRECT_URI,
                    'code': code,
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            ),
            delete_key_redis(f'hubspot_state:{org_id}:{user_id}'),
        )

    await add_key_value_redis(
        f'hubspot_credentials:{org_id}:{user_id}',
        json.dumps(response.json()),
        expire=600,
    )

    close_window_script = """
    <html>
        <script>
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=close_window_script)
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
cd backend
./venv/bin/python -m pytest tests/test_hubspot.py::test_oauth2callback_hubspot_exchanges_code_and_stores_credentials -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/hubspot.py backend/tests/test_hubspot.py
git commit -m "feat(hubspot): implement oauth2callback_hubspot token exchange"
```

---

### Task 3: Implement `get_hubspot_credentials` (backend)

**Files:**
- Modify: `backend/integrations/hubspot.py` (replace `get_hubspot_credentials` body).
- Modify: `backend/tests/test_hubspot.py` (append two tests).

- [ ] **Step 1: Append the failing tests**

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd backend
./venv/bin/python -m pytest tests/test_hubspot.py -k get_hubspot_credentials -v
```

Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Replace `get_hubspot_credentials` in `backend/integrations/hubspot.py`**

```python
async def get_hubspot_credentials(user_id, org_id):
    credentials = await get_value_redis(f'hubspot_credentials:{org_id}:{user_id}')
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    credentials = json.loads(credentials)
    await delete_key_redis(f'hubspot_credentials:{org_id}:{user_id}')
    return credentials
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
cd backend
./venv/bin/python -m pytest tests/test_hubspot.py -k get_hubspot_credentials -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/hubspot.py backend/tests/test_hubspot.py
git commit -m "feat(hubspot): implement get_hubspot_credentials"
```

---

### Task 4: Implement `create_integration_item_metadata_object` (backend)

**Files:**
- Modify: `backend/integrations/hubspot.py` (replace placeholder).
- Modify: `backend/tests/test_hubspot.py` (append tests).

- [ ] **Step 1: Append the failing tests**

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd backend
./venv/bin/python -m pytest tests/test_hubspot.py -k create_integration_item_metadata_object -v
```

Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Replace `create_integration_item_metadata_object` in `backend/integrations/hubspot.py`**

```python
def create_integration_item_metadata_object(response_json, item_type):
    properties = response_json.get('properties') or {}

    if item_type == 'contact':
        first = properties.get('firstname') or ''
        last = properties.get('lastname') or ''
        name = f'{first} {last}'.strip() or properties.get('email')
    elif item_type == 'company':
        name = properties.get('name') or properties.get('domain')
    elif item_type == 'deal':
        name = properties.get('dealname')
    else:
        name = properties.get('name')

    item_id = response_json.get('id')
    if not name:
        name = f'{item_type} {item_id}'

    return IntegrationItem(
        id=f'{item_id}_{item_type}',
        type=item_type,
        name=name,
        creation_time=response_json.get('createdAt'),
        last_modified_time=response_json.get('updatedAt'),
        url=f'https://app.hubspot.com/contacts/_/{item_type}/{item_id}' if item_id else None,
    )
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
cd backend
./venv/bin/python -m pytest tests/test_hubspot.py -k create_integration_item_metadata_object -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/integrations/hubspot.py backend/tests/test_hubspot.py
git commit -m "feat(hubspot): map HubSpot CRM responses to IntegrationItem"
```

---

### Task 5: Implement `get_items_hubspot` (backend)

**Files:**
- Modify: `backend/integrations/hubspot.py` (replace placeholder + add endpoint table).
- Modify: `backend/tests/test_hubspot.py` (append test).

- [ ] **Step 1: Append the failing test**

```python
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
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd backend
./venv/bin/python -m pytest tests/test_hubspot.py::test_get_items_hubspot_aggregates_objects -v
```

Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Replace `get_items_hubspot` in `backend/integrations/hubspot.py`**

Add this constant near the other module-level constants:

```python
HUBSPOT_OBJECT_ENDPOINTS = [
    ('contact', 'https://api.hubapi.com/crm/v3/objects/contacts'),
    ('company', 'https://api.hubapi.com/crm/v3/objects/companies'),
    ('deal', 'https://api.hubapi.com/crm/v3/objects/deals'),
]
```

Replace `get_items_hubspot` with:

```python
def get_items_hubspot(credentials):
    credentials = json.loads(credentials) if isinstance(credentials, str) else credentials
    access_token = credentials.get('access_token')
    headers = {'Authorization': f'Bearer {access_token}'}

    items: list[IntegrationItem] = []
    for item_type, url in HUBSPOT_OBJECT_ENDPOINTS:
        next_after = None
        while True:
            params = {'limit': 100}
            if next_after:
                params['after'] = next_after
            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                break
            body = response.json()
            for result in body.get('results', []):
                items.append(create_integration_item_metadata_object(result, item_type))
            next_after = body.get('paging', {}).get('next', {}).get('after')
            if not next_after:
                break

    print(f'hubspot integration items: {items}')
    return items
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
cd backend
./venv/bin/python -m pytest tests/test_hubspot.py::test_get_items_hubspot_aggregates_objects -v
```

Expected: PASS.

- [ ] **Step 5: Run the full hubspot test file**

```bash
cd backend
./venv/bin/python -m pytest tests/test_hubspot.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/integrations/hubspot.py backend/tests/test_hubspot.py
git commit -m "feat(hubspot): fetch contacts/companies/deals via CRM v3"
```

---

### Task 6: Align HubSpot route in `main.py` with the airtable/notion convention

**Files:**
- Modify: `backend/main.py:75-77`.

The current handler is registered at `/integrations/hubspot/get_hubspot_items` and has `await get_items_hubspot(credentials)`. The frontend `data-form.js` builds URLs as `/integrations/<lower>/load`, and `get_items_hubspot` is synchronous (mirrors `get_items_airtable`). Both must change.

- [ ] **Step 1: Edit `backend/main.py`**

Find this block at lines 75-77:

```python
@app.post('/integrations/hubspot/get_hubspot_items')
async def load_slack_data_integration(credentials: str = Form(...)):
    return await get_items_hubspot(credentials)
```

Replace with:

```python
@app.post('/integrations/hubspot/load')
async def get_hubspot_items(credentials: str = Form(...)):
    return get_items_hubspot(credentials)
```

- [ ] **Step 2: Verify the backend imports cleanly**

```bash
cd backend
./venv/bin/python -c "import main"
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "refactor(hubspot): align load route with airtable/notion convention"
```

---

### Task 7: Create `frontend/src/integrations/hubspot.js`

**Files:**
- Create: `frontend/src/integrations/hubspot.js`.
- Delete: `frontend/src/integrations/slack.js`.

- [ ] **Step 1: Create `frontend/src/integrations/hubspot.js`**

```javascript
// hubspot.js

import { useState, useEffect } from 'react';
import {
    Box,
    Button,
    CircularProgress
} from '@mui/material';
import axios from 'axios';

export const HubspotIntegration = ({ user, org, integrationParams, setIntegrationParams }) => {
    const [isConnected, setIsConnected] = useState(false);
    const [isConnecting, setIsConnecting] = useState(false);

    const handleConnectClick = async () => {
        try {
            setIsConnecting(true);
            const formData = new FormData();
            formData.append('user_id', user);
            formData.append('org_id', org);
            const response = await axios.post(`http://localhost:8000/integrations/hubspot/authorize`, formData);
            const authURL = response?.data;

            const newWindow = window.open(authURL, 'HubSpot Authorization', 'width=600, height=600');

            const pollTimer = window.setInterval(() => {
                if (newWindow?.closed !== false) {
                    window.clearInterval(pollTimer);
                    handleWindowClosed();
                }
            }, 200);
        } catch (e) {
            setIsConnecting(false);
            alert(e?.response?.data?.detail);
        }
    };

    const handleWindowClosed = async () => {
        try {
            const formData = new FormData();
            formData.append('user_id', user);
            formData.append('org_id', org);
            const response = await axios.post(`http://localhost:8000/integrations/hubspot/credentials`, formData);
            const credentials = response.data;
            if (credentials) {
                setIsConnecting(false);
                setIsConnected(true);
                setIntegrationParams(prev => ({ ...prev, credentials: credentials, type: 'HubSpot' }));
            }
            setIsConnecting(false);
        } catch (e) {
            setIsConnecting(false);
            alert(e?.response?.data?.detail);
        }
    };

    useEffect(() => {
        setIsConnected(integrationParams?.credentials ? true : false);
    }, []);

    return (
        <>
        <Box sx={{mt: 2}}>
            Parameters
            <Box display='flex' alignItems='center' justifyContent='center' sx={{mt: 2}}>
                <Button
                    variant='contained'
                    onClick={isConnected ? () => {} : handleConnectClick}
                    color={isConnected ? 'success' : 'primary'}
                    disabled={isConnecting}
                    style={{
                        pointerEvents: isConnected ? 'none' : 'auto',
                        cursor: isConnected ? 'default' : 'pointer',
                        opacity: isConnected ? 1 : undefined
                    }}
                >
                    {isConnected ? 'HubSpot Connected' : isConnecting ? <CircularProgress size={20} /> : 'Connect to HubSpot'}
                </Button>
            </Box>
        </Box>
        </>
    );
};
```

- [ ] **Step 2: Delete the leftover `slack.js`**

```bash
rm frontend/src/integrations/slack.js
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/integrations/hubspot.js frontend/src/integrations/slack.js
git commit -m "feat(hubspot): add HubspotIntegration React component"
```

---

### Task 8: Wire HubSpot into `IntegrationForm` and `DataForm`

**Files:**
- Modify: `frontend/src/integration-form.js:7-14`.
- Modify: `frontend/src/data-form.js:9-12`.

- [ ] **Step 1: Edit `frontend/src/integration-form.js`**

Find lines 7-14:

```javascript
import { AirtableIntegration } from './integrations/airtable';
import { NotionIntegration } from './integrations/notion';
import { DataForm } from './data-form';

const integrationMapping = {
    'Notion': NotionIntegration,
    'Airtable': AirtableIntegration,
};
```

Replace with:

```javascript
import { AirtableIntegration } from './integrations/airtable';
import { NotionIntegration } from './integrations/notion';
import { HubspotIntegration } from './integrations/hubspot';
import { DataForm } from './data-form';

const integrationMapping = {
    'Notion': NotionIntegration,
    'Airtable': AirtableIntegration,
    'HubSpot': HubspotIntegration,
};
```

- [ ] **Step 2: Edit `frontend/src/data-form.js`**

Find lines 9-12:

```javascript
const endpointMapping = {
    'Notion': 'notion',
    'Airtable': 'airtable',
};
```

Replace with:

```javascript
const endpointMapping = {
    'Notion': 'notion',
    'Airtable': 'airtable',
    'HubSpot': 'hubspot',
};
```

- [ ] **Step 3: Verify the frontend builds**

```bash
cd frontend
npm install --silent
CI=true npm run build 2>&1 | tail -20
```

Expected: `Compiled successfully` (warnings about unused imports are OK).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/integration-form.js frontend/src/data-form.js
git commit -m "feat(hubspot): expose HubSpot in IntegrationForm and DataForm"
```

---

### Task 9: End-to-end manual verification

**Files:** none modified.

Requires the HubSpot dev account from **Prerequisites**.

- [ ] **Step 1: Set HubSpot credentials in `backend/integrations/hubspot.py`**

Edit the `CLIENT_ID` and `CLIENT_SECRET` constants near the top of `backend/integrations/hubspot.py` to your HubSpot dev app's values. Do **not** commit them — leave the diff staged locally and revert before any final commit if you want to keep secrets out of git history.

- [ ] **Step 2: Start dependencies in three terminals**

Terminal A (Redis):
```bash
redis-server
```

Terminal B (backend):
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload
```

Terminal C (frontend):
```bash
cd frontend
npm install
npm start
```

- [ ] **Step 3: Drive the OAuth flow in the browser**

1. Open `http://localhost:3000`.
2. Set User=`TestUser`, Organization=`TestOrg`.
3. Pick `HubSpot` from the **Integration Type** dropdown.
4. Click **Connect to HubSpot**. The popup should load HubSpot's OAuth consent screen.
5. Approve. The popup closes automatically; the button should turn green ("HubSpot Connected").
6. Click **Load Data**.

- [ ] **Step 4: Verify items in the backend log**

Check Terminal B's uvicorn output. Expected: a line like

```
hubspot integration items: [<integrations.integration_item.IntegrationItem object at ...>, ...]
```

The list should be non-empty if the dev portal account has any contacts/companies/deals (HubSpot's developer test accounts come pre-seeded with sample data).

- [ ] **Step 5: Clean up**

If you want to omit the real CLIENT_ID/CLIENT_SECRET from your final commit, restore the placeholder `'XXX'` values:

```bash
git diff backend/integrations/hubspot.py
# verify only credential lines are dirty, then
git checkout -- backend/integrations/hubspot.py  # if you only want to revert that file
```

Or commit them and rotate later. The assessment file `airtable.py` already has live-looking credentials checked in, so either choice is consistent with the repo's existing posture.

---

## Self-review

**Spec coverage**

| Spec requirement | Tasks |
| --- | --- |
| Part 1 — `authorize_hubspot` | Task 1 |
| Part 1 — `oauth2callback_hubspot` | Task 2 |
| Part 1 — `get_hubspot_credentials` | Task 3 |
| Part 1 — frontend `hubspot.js` exists and matches existing pattern | Task 7 |
| Part 1 — HubSpot reachable from the UI | Task 8 |
| Part 2 — `get_items_hubspot` returns `IntegrationItem` list | Tasks 4 + 5 |
| Part 2 — print final list to console | Task 5 (Step 3, `print(...)`) and Task 9 (Step 4) |
| HubSpot client id/secret created by candidate | Prerequisites + Task 9 Step 1 |

**Placeholder scan:** every code block contains real code; no "TODO", "fill in details", or "similar to Task N" stand-ins. Test inputs and expected outputs are concrete.

**Type/name consistency:** `authorize_hubspot`, `oauth2callback_hubspot`, `get_hubspot_credentials`, `create_integration_item_metadata_object(response_json, item_type)`, and `get_items_hubspot(credentials)` are referenced consistently across tasks and match the names already imported by `backend/main.py`. Frontend uses `HubspotIntegration` consistently across `hubspot.js` and `integration-form.js`. `endpointMapping` value `'hubspot'` matches the new route `/integrations/hubspot/load` in `main.py`.
