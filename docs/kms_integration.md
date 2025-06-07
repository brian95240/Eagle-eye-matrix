# Eagle Eye Matrix: Key Management Service (KMS) Integration Documentation

## Introduction

Secure access control is fundamental to the Eagle Eye Matrix (EEM) system, especially for services that interact with potentially sensitive data or external APIs, such as the Public Records Adapters. The EEM Key Management Service (KMS) is designed to provide a centralized mechanism for managing the lifecycle and validation of API keys used by various EEM microservices. This document details the current placeholder implementation of the KMS and its integration with other services, specifically the Public Records Adapters.

## KMS Placeholder Overview

The current KMS implementation, located at `/home/ubuntu/eagle_eye_matrix/services/security/src/kms`, serves as a functional **placeholder**. It simulates the core responsibilities of a KMS but lacks the robust security features of a production-grade system (as envisioned in the full Phase 10 plan, such as HSM integration, zero-exposure architecture, automated rotation, and secure destruction).

**Purpose**: To provide a basic, centralized API for:
1.  Generating new API keys associated with specific EEM services.
2.  Validating API keys presented by services attempting to access protected resources.

**Functionality**:
*   **Key Generation**: Creates unique API keys (UUIDs in the current implementation) and stores them in an in-memory dictionary, associating each key with a specific service name (e.g., `vital-records-adapter`).
*   **Key Validation**: Checks if a provided API key exists in its in-memory store and optionally verifies if it's associated with the expected service.
*   **In-Memory Storage**: All keys are stored in a simple Python dictionary within the running KMS process. **This is not secure and keys are lost upon service restart.**

**API Endpoints**:
*   `POST /keys/generate`: Accepts a service name and returns a newly generated API key for that service.
*   `POST /keys/validate`: Accepts an API key (`key_value`) and optionally a service name. Returns whether the key is valid and, if provided, associated with the correct service.
*   `GET /health`: Basic health check endpoint.

## Integration with Public Records Adapters

The Public Records Adapters (Vital, Voting, Tax, Property) are the primary examples of services integrated with the KMS placeholder. This integration enforces that only authorized clients (possessing a valid API key) can query these adapters.

**Integration Pattern**:
1.  **API Key Requirement**: Clients calling the `/query` endpoint of any Public Records Adapter MUST include the API key in the `X-API-Key` HTTP header.
2.  **FastAPI Dependency**: Each adapter utilizes a FastAPI dependency function (`verify_api_key`) injected into its `/query` endpoint.
3.  **Validation Call**: The `verify_api_key` function extracts the key from the `X-API-Key` header.
4.  **KMS Communication**: It then makes an asynchronous HTTP POST request to the KMS service's `/keys/validate` endpoint, sending the extracted API key.
5.  **Authorization Decision**: Based on the response from the KMS (`is_valid` flag and `service_name` match), the dependency either allows the request to proceed to the adapter's query logic or raises an HTTP 401 (Unauthorized) or 403 (Forbidden) error, preventing the query.
6.  **Error Handling**: The dependency includes error handling for cases where the KMS is unreachable (HTTP 503) or other unexpected errors occur during validation (HTTP 500).

**Example Flow (Tax Records Query)**:
1.  Client sends POST request to `http://<tax-adapter-host>:8042/query` with `X-API-Key: <api-key-value>` header and query payload.
2.  FastAPI routes request to `query_tax_records`.
3.  The `Depends(verify_api_key)` mechanism triggers.
4.  `verify_api_key` extracts `<api-key-value>`.
5.  `verify_api_key` sends POST to `http://<kms-host>:8050/keys/validate` with `{"key_value": "<api-key-value>"}`.
6.  KMS checks its internal store for the key and its association with `tax_records_adapter`.
7.  KMS responds (e.g., `{"is_valid": true, "key_id": "xyz", "service_name": "tax_records_adapter"}`).
8.  `verify_api_key` receives a valid response, allows request processing to continue.
9.  `query_tax_records` executes its placeholder logic and returns results.

## Limitations and Future Work

As mentioned, this KMS is a placeholder. Key limitations include:
*   **Insecure Storage**: Keys are stored in memory and lost on restart.
*   **No Rotation/Expiration**: Keys are static and never expire or rotate automatically.
*   **No Auditing**: Lacks detailed, tamper-evident logs of key generation or validation events.
*   **No Real Security**: Does not implement HSM integration, envelope encryption, zero-exposure principles, etc.

Implementing the full **Phase 10: Advanced API Key Security System** is necessary to address these limitations and provide a production-ready, secure key management infrastructure for the EEM system. This would involve replacing this placeholder with a robust service incorporating hardware security modules, automated lifecycle management, comprehensive auditing, and zero-exposure design patterns.

