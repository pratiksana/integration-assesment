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

CLIENT_ID = '325706c3-2816-445d-bfc5-303f7aff7533'
CLIENT_SECRET = 'b8535d89-9de5-44b1-987d-50847cc89557'
REDIRECT_URI = 'http://localhost:8000/integrations/hubspot/oauth2callback'
SCOPES = 'crm.objects.contacts.read crm.objects.companies.read crm.objects.deals.read'
AUTHORIZATION_URL = 'https://app.hubspot.com/oauth/authorize'
TOKEN_URL = 'https://api.hubapi.com/oauth/v1/token'

HUBSPOT_OBJECT_ENDPOINTS = [
    ('contact', 'https://api.hubapi.com/crm/v3/objects/contacts'),
    ('company', 'https://api.hubapi.com/crm/v3/objects/companies'),
    ('deal', 'https://api.hubapi.com/crm/v3/objects/deals'),
]


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


async def get_hubspot_credentials(user_id, org_id):
    credentials = await get_value_redis(f'hubspot_credentials:{org_id}:{user_id}')
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    credentials = json.loads(credentials)
    await delete_key_redis(f'hubspot_credentials:{org_id}:{user_id}')
    return credentials


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