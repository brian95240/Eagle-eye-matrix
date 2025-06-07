# Eagle Eye Matrix: Public Records Subsystem Documentation

## Introduction

The Public Records Subsystem is a critical component of the Eagle Eye Matrix (EEM) Open Source Intelligence (OSINT) platform. Its primary function is to provide a standardized interface for querying various external public record databases, thereby enriching the identity profiles and investigation timelines managed by other EEM subsystems. This subsystem acts as a bridge between the core EEM framework and the vast, often disparate, world of publicly available information, such as vital statistics, government records, and property data. By integrating these external data sources, the EEM system can significantly enhance its ability to track individuals, verify identities, and uncover connections relevant to an investigation.

## Architecture Overview

The Public Records Subsystem employs a microservice-based architecture, specifically utilizing a pattern of dedicated 'Adapters'. Each adapter is a distinct microservice responsible for interacting with a specific type of public record source or API. This modular design offers several advantages:

1.  **Isolation**: Issues or changes within one adapter (e.g., due to an external API update) do not directly impact others.
2.  **Scalability**: Individual adapters can be scaled independently based on the demand for specific record types.
3.  **Maintainability**: Development and maintenance can focus on specific adapters without requiring knowledge of the entire subsystem.
4.  **Extensibility**: Adding support for new public record types simply involves creating and deploying a new adapter service.

Currently, the subsystem includes placeholder adapters for the following record types:

*   **Vital Records Adapter**: Simulates access to birth, death, and marriage records.
*   **Voting Records Adapter**: Simulates access to voter registration details and history.
*   **Tax Records Adapter**: Simulates access to tax filing information (using highly abstracted placeholders).
*   **Property Records Adapter**: Simulates access to property ownership and assessment data.

These adapters expose standardized RESTful APIs (primarily a `/query` endpoint) that accept specific search criteria and return structured results. They are designed to be invoked primarily by the EEM Credential Verifier service, which orchestrates the process of validating identity attributes against various sources.

## Interaction with EEM Core

The Public Records Subsystem integrates seamlessly with the broader EEM ecosystem:

*   **Credential Verifier**: This service, part of the Identity Management Subsystem, is the primary consumer of the Public Records Adapters. When a verification task requires checking public records (e.g., verifying an address against property records or checking registration status via voting records), the Credential Verifier identifies the appropriate adapter and sends a query request.
*   **Event Bus**: While the adapters themselves are primarily request/response based via their APIs, future enhancements could involve them publishing events (e.g., discovery of a significant record change) onto the EEM event bus for consumption by other services like the Trigger Engine or Identity Aggregator.
*   **Key Management Service (KMS)**: Crucially, all Public Records Adapters are integrated with the EEM KMS (currently a placeholder). Access to each adapter's API requires a valid API key, which is verified against the KMS before any query is processed. This ensures that access to potentially sensitive public record queries is controlled and auditable.

## Data Handling and Placeholders

It is essential to understand that the current implementation of the Public Records Adapters utilizes **placeholder data and logic**. They do not connect to real external databases. The data structures and query responses are designed to mimic realistic scenarios but are entirely simulated. This approach was taken for several reasons:

*   **Development Speed**: Allows for rapid development and testing of the integration patterns without needing access credentials or handling the complexities of real-world APIs.
*   **Cost**: Avoids potential costs associated with querying commercial or government databases.
*   **Legal/Ethical Compliance**: Prevents accidental access to or processing of real public records during development and testing, ensuring compliance with privacy regulations and terms of service.

When transitioning to a production environment, each placeholder adapter would need to be replaced or significantly modified to interact with the actual external APIs or data sources for the specific record types it represents. This would involve handling authentication, rate limiting, error handling, data parsing, and legal compliance specific to each source.

## Security Integration

Security is a paramount concern when dealing with public records. The integration with the EEM Key Management Service (KMS) is the first layer of defense. Every request to a Public Records Adapter must include a valid API key provided in the `X-API-Key` header. The adapter then communicates with the KMS to validate this key, ensuring it is active and authorized for the specific adapter service. This prevents unauthorized access and provides a mechanism for auditing and revoking access if necessary. Further details on the KMS and the integration mechanism are provided in separate documentation sections.

## Future Directions

Potential future enhancements for the Public Records Subsystem include:

*   **Real Adapter Implementation**: Replacing placeholders with functional adapters for specific, legally accessible public data sources.
*   **Correlation Engine**: Developing a dedicated service within the subsystem or enhancing the Credential Verifier/Identity Aggregator to perform more sophisticated cross-record correlation and identity resolution.
*   **Event Publication**: Enabling adapters to publish significant findings (e.g., address change detected in voter records) to the EEM event bus.
*   **Enhanced Compliance**: Integrating more robust logging and auditing specific to public data access regulations (e.g., DPPA for driver records, if implemented).
*   **Caching**: Implementing caching mechanisms within adapters to reduce redundant queries to external sources and improve performance.

