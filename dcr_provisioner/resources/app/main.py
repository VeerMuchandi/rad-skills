import os
import base64
import json
import logging
import time
from typing import Optional, Dict, Any
import httpx
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from google.auth import default
from google.auth.transport.requests import Request as GoogleRequest
from google.cloud import firestore
from google.cloud import secretmanager
from jose import jwt as jose_jwt, JWTError

# --- Logger ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- Configuration ---
# --- Configuration ---
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
PROVIDER_URL = os.environ.get("PROVIDER_URL")  # e.g., https://api.mycompany.com
PROVIDER_ID = os.environ.get("PROVIDER_ID")    # e.g., my-company-partner
IDP_TYPE = os.environ.get("IDP_TYPE", "Okta")  # e.g., Okta, Auth0, Custom
IDP_DOMAIN = os.environ.get("IDP_DOMAIN")      # e.g., https://dev-XXXXXX.okta.com
DEFAULT_REDIRECT_URI = os.environ.get(
    "DEFAULT_REDIRECT_URI",
    "https://vertexaisearch.cloud.google.com/oauth-redirect"
)

GOOGLE_CERT_URL = "https://www.googleapis.com/service_accounts/v1/metadata/x509/cloud-agentspace@system.gserviceaccount.com"
CERT_CACHE: Dict[str, Any] = {}

# Initialize Google Cloud Clients
db = firestore.Client()
secret_client = secretmanager.SecretManagerServiceClient()

# --- Helper: Fetch IdP API Token from Secret Manager ---
def get_idp_api_token() -> str:
    secret_name = f"projects/{PROJECT_ID}/secrets/idp-api-token/versions/latest"
    try:
        response = secret_client.access_secret_version(request={"name": secret_name})
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logger.error(f"Failed to access Secret Manager for IdP Token: {e}")
        raise RuntimeError("Configuration error: Secure credentials inaccessible.")

# --- Helper: Google JWT Validation ---
async def get_google_public_keys(iss: str) -> Dict[str, Any]:
    cached_entry = CERT_CACHE.get(iss)
    current_time = time.time()
    if cached_entry and cached_entry["expires"] > current_time:
        return cached_entry["keys"]

    logger.info(f"Fetching Google public keys from {iss}")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(iss)
            response.raise_for_status()
            certs = response.json()
            # Cache for 1 hour
            CERT_CACHE[iss] = {"keys": certs, "expires": current_time + 3600}
            return certs
        except Exception as e:
            logger.error(f"Error fetching certs from {iss}: {e}")
            raise HTTPException(status_code=500, detail="Could not fetch verification keys.")

async def validate_google_jwt(jwt_token: str) -> dict:
    try:
        unverified_header = jose_jwt.get_unverified_header(jwt_token)
        kid = unverified_header.get("kid")
        unverified_claims = jose_jwt.get_unverified_claims(jwt_token)
        issuer = unverified_claims.get("iss")

        if issuer != GOOGLE_CERT_URL:
            raise JWTError("Invalid token issuer.")

        public_keys = await get_google_public_keys(issuer)
        if kid not in public_keys:
            raise JWTError("Verification key not found.")

        cert_pem = public_keys[kid]
        decoded_jwt = jose_jwt.decode(
            jwt_token,
            cert_pem,
            algorithms=["RS256"],
            audience=PROVIDER_URL
        )
        return decoded_jwt
    except JWTError as e:
        logger.error(f"JWT Verification failed: {e}")
        raise HTTPException(status_code=400, detail=f"JWT Validation failed: {str(e)}")

# --- Helper: Identity Provider (IdP) Client Registration ---
async def register_idp_client(order_id: str, redirect_uris: list[str]) -> tuple[str, str]:
    """
    Registers a new OAuth client in the selected Identity Provider.
    The template below is configured for Okta. If using Auth0 or a custom server,
    the agent executing the skill will modify this function to match your IdP's API.
    """
    idp_token = get_idp_api_token()
    
    if IDP_TYPE.lower() == "okta":
        headers = {
            "Authorization": f"SSWS {idp_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        client_payload = {
            "client_name": f"Gemini Agent - Order {order_id}",
            "application_type": "web",
            "redirect_uris": redirect_uris,
            "response_types": ["code"],
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "client_secret_post"
        }
        logger.info(f"Registering client in Okta for Order: {order_id}")
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{IDP_DOMAIN}/oauth2/v1/clients", json=client_payload, headers=headers)
            response.raise_for_status()
            okta_client = response.json()
            return okta_client.get("client_id"), okta_client.get("client_secret")
            
    elif IDP_TYPE.lower() == "auth0":
        # Auth0 DCR implementation placeholder (RFC 7591)
        # headers = {"Authorization": f"Bearer {idp_token}", ...}
        # ...
        raise NotImplementedError("Auth0 DCR is not implemented in this template yet.")
        
    else:
        # Custom IdP implementation
        raise NotImplementedError(f"DCR for IdP type '{IDP_TYPE}' is not implemented.")

async def deprovision_idp_client(client_id: str):
    """
    Deactivates and deletes the OAuth client from the selected Identity Provider.
    """
    idp_token = get_idp_api_token()
    
    if IDP_TYPE.lower() == "okta":
        headers = {
            "Authorization": f"SSWS {idp_token}",
            "Accept": "application/json"
        }
        logger.info(f"Deprovisioning client in Okta: {client_id}")
        async with httpx.AsyncClient() as client:
            # 1. Deactivate client
            await client.post(f"{IDP_DOMAIN}/oauth2/v1/clients/{client_id}/lifecycle/deactivate", headers=headers)
            # 2. Delete client
            await client.delete(f"{IDP_DOMAIN}/oauth2/v1/clients/{client_id}", headers=headers)
            
    elif IDP_TYPE.lower() == "auth0":
        # Auth0 deprovisioning logic
        pass
        
    else:
        raise NotImplementedError(f"Deprovisioning for IdP type '{IDP_TYPE}' is not implemented.")

# --- Helper: Google Procurement API Operations ---
async def get_procurement_client():
    credentials, project = default()
    credentials.refresh(GoogleRequest())
    return httpx.AsyncClient(headers={"Authorization": f"Bearer {credentials.token}"})

async def approve_marketplace_account(provider_id: str, account_id: str):
    logger.info(f"Approving Marketplace Account: {account_id}")
    client = await get_procurement_client()
    url = f"https://cloudcommerceprocurement.googleapis.com/v1/providers/{provider_id}/accounts/{account_id}:approve"
    response = await client.post(url, json={"reason": "Approved via DCR Provisioner Webhook"})
    response.raise_for_status()

async def verify_entitlement_status(provider_id: str, entitlement_id: str) -> str:
    logger.info(f"Verifying Entitlement Status from Google: {entitlement_id}")
    client = await get_procurement_client()
    url = f"https://cloudcommerceprocurement.googleapis.com/v1/providers/{provider_id}/entitlements/{entitlement_id}"
    response = await client.get(url)
    response.raise_for_status()
    return response.json().get("state")

# --- Database Operations ---
def get_entitlement(order_id: str) -> Optional[dict]:
    doc = db.collection("entitlements").document(order_id).get()
    return doc.to_dict() if doc.exists else None

def save_entitlement(order_id: str, data: dict):
    db.collection("entitlements").document(order_id).set(data, merge=True)

# --- Models ---
class RegistrationRequest(BaseModel):
    software_statement: str

class DCRResponse(BaseModel):
    client_id: str
    client_secret: str
    client_secret_expires_at: int = 0

# --- Main Hybrid Webhook Endpoint ---
@app.post("/dcr")
async def handle_dcr_or_pubsub(request: Request):
    body = await request.json()

    # --- Path A: Dynamic Client Registration (DCR) ---
    if "software_statement" in body:
        logger.info("Handling DCR Request...")
        reg_request = RegistrationRequest(**body)
        decoded_token = await validate_google_jwt(reg_request.software_statement)

        order_id = decoded_token.get("google", {}).get("order")
        redirect_uris = decoded_token.get("auth_app_redirect_uris")

        if not order_id or not redirect_uris:
            raise HTTPException(status_code=400, detail="Missing required claims in JWT.")

        # Check Firestore
        record = get_entitlement(order_id)
        if record and record.get("state") == "ACTIVE":
            return DCRResponse(
                client_id=record["client_id"],
                client_secret=record["client_secret"]
            )

        # Resiliency Fallback: Lazy Provisioning
        logger.warning(f"Order {order_id} not found in database. Initiating Lazy Provisioning Fallback...")
        try:
            state = await verify_entitlement_status(PROVIDER_ID, order_id)
            if state == "ENTITLEMENT_ACTIVE":
                client_id, client_secret = await register_idp_client(order_id, redirect_uris)
                save_entitlement(order_id, {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "state": "ACTIVE",
                    "redirect_uris": redirect_uris,
                    "updated_time": firestore.SERVER_TIMESTAMP
                })
                return DCRResponse(client_id=client_id, client_secret=client_secret)
        except Exception as e:
            logger.error(f"Lazy provisioning failed for Order {order_id}: {e}")
            
        raise HTTPException(status_code=400, detail="Order not active or not provisioned.")

    # --- Path B: Pub/Sub Marketplace Event ---
    if "message" in body:
        logger.info("Handling Pub/Sub Event...")
        try:
            message_data = body["message"]["data"]
            decoded_data = base64.b64decode(message_data).decode("utf-8")
            payload = json.loads(decoded_data)
            event_type = payload.get("eventType")
            
            logger.info(f"Received Event: {event_type}")

            # 1. Handle Account Creation
            if event_type == "ACCOUNT_CREATION_REQUESTED":
                account_id = payload.get("account", {}).get("id")
                await approve_marketplace_account(PROVIDER_ID, account_id)
                return {"status": "success", "action": "account_approved"}

            # 2. Handle Entitlement Creation (Proactive Provisioning)
            if event_type == "ENTITLEMENT_CREATION_REQUESTED":
                order_id = payload.get("entitlement", {}).get("id")
                
                # Proactively create OAuth client
                client_id, client_secret = await register_idp_client(order_id, [DEFAULT_REDIRECT_URI])
                save_entitlement(order_id, {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "state": "ACTIVE",
                    "redirect_uris": [DEFAULT_REDIRECT_URI],
                    "created_time": firestore.SERVER_TIMESTAMP
                })
                return {"status": "success", "action": "entitlement_provisioned", "orderId": order_id}

            # 3. Handle Entitlement Cancellation (Deprovisioning)
            if event_type in ["ENTITLEMENT_CANCELLED", "ENTITLEMENT_DELETED"]:
                order_id = payload.get("entitlement", {}).get("id")
                record = get_entitlement(order_id)
                if record:
                    await deprovision_idp_client(record["client_id"])
                    save_entitlement(order_id, {
                        "state": "CANCELLED",
                        "updated_time": firestore.SERVER_TIMESTAMP
                    })
                return {"status": "success", "action": "entitlement_deprovisioned", "orderId": order_id}

            return {"status": "ignored", "reason": "unhandled_event_type"}
        except Exception as e:
            logger.error(f"Failed to process Pub/Sub event: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal processing error.")

    raise HTTPException(status_code=400, detail="Invalid request format.")

@app.get("/health")
def health_check():
    return {"status": "healthy"}
