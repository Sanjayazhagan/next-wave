# Browser ↔ agent ↔ WhatsApp/core wiring

Implemented transport boundary: /integration/v2/conversation. This module does not run LangGraph, call a model, accept a public provider webhook or send a WhatsApp message. Core owns those services. It queues typed citizen requests and validates correlated replies so browser execution can pause safely.

## Responsibilities

Browser provides page observations/actions, generation-bound pauses, human-assistance paths where an adapter exists, encrypted artifacts, review/result interfaces and durable events. Core maps the citizen's WhatsApp identity to an opaque subject, runs the model/graph, asks questions, verifies provider webhooks, sends messages, resumes its graph and makes actual consent/eligibility/doctor/approval decisions. Remote provides extraction/rules/language/compression/doctor services. Core can also consume this transport from a web/chat service; it is provider-neutral.

## Core graph wiring

1. Create a v1 adapter session or a v2 general context. Persist its ID/generation in core's graph checkpoint. GET /integration/v2/conversation/executions/{id} returns the browser binding (context_id, generation, subject, execution_type).
2. A model decision needs_information is a pause, not permission to invent values. Map requested field IDs to typed Question objects. ConversationClient.ask_from_decision accepts the validated decision/binding and requires the question IDs to cover the model request. POST /interrupts creates the durable request and one delivery.
3. Checkpoint the interrupt_id/request_id in core, then pause its graph. The browser rejects mutations while a request is pending/processing or needs reconciliation. Reads/observations remain available. Core must resolve/cancel/reconcile the request before resuming actions.
4. A core/n8n delivery worker POSTs /deliveries/claim with a stable consumer_id. It receives a delivery_id, typed encrypted-at-rest message payload, lease_token and expiry. It uses its own WhatsApp provider to send the prompt/fields/assistance link. No service credential belongs in the citizen message.
5. After provider acceptance, POST /deliveries/{id}/ack with consumer_id, lease_token and real provider_message_id. The lease is 60 seconds; a crashed worker's unacknowledged delivery can be reclaimed. Delivery is at-least-once: the consumer must deduplicate delivery_id and reconcile the provider result after a crash. ACK is the trusted consumer's report, not independent proof that the citizen read a message. Expired requests must not be sent.
6. Core receives and authenticates the real WhatsApp webhook. It derives subject from its verified account mapping, never from user-provided text, and resolves the original interrupt_id via the message/reply correlation. POST /interrupts/{id}/responses uses a stable response_id (e.g. mapped provider message ID), subject, generation and the typed reply. Wrong recipients, stale generations, unknown fields, invalid choices/dates/numbers and expired/duplicate requests are handled explicitly.
7. GET /interrupts/{id}/response returns the correlated answer for core's graph. Information is marked citizen_provided_not_document_verified: extraction/doctor/verification still belongs to core/remote. Core explicitly verifies or confirms the value before issuing a browser fill with verified/source provenance. A received answer is not automatically considered document-verified.

Python SDK: clients/conversation_client.py. Node/server-side SDK: clients/conversation_client.mjs. Schemas: contracts/v2/conversation-*.json, citizen-*.json and delivery-*.json; the full current OpenAPI includes every route. An executable Node example and scripts/verify_conversation.py exercise the exact HTTP contract without contacting a provider.

## Request types

- information: named bounded text/number/date/choice/artifact questions. Artifact answers must resolve to artifacts owned by this browser context. Secrets cannot be requested through ordinary information fields.
- otp: supported only through the existing tested v1 authentication adapter; relayed transiently to the actual worker. Neither the value nor a low-entropy OTP hash is stored in the request/response/delivery ledger. Repeated response IDs replay only the safe processed-result metadata, including failed attempts, without resending the secret.
- captcha: supported through the tested v1 human adapter. Creation queues its actual secure assistance path. The person can use that page; its live completion propagates to the conversation request. A text answer can use the dedicated reply path only before another human controller claims the page. This is not universal CAPTCHA support.
- device_auth: fails explicitly until a reviewed portal/device adapter exists. No fake completion or face-auth emulation is used.
- helper: queues a request for human assistance and allows core to record its response; it does not grant arbitrary remote browser controls.
- approval: binds the decision to the declared exact review_hash and generation. For v1 the current stored browser review must match. Core can retrieve approve/edit/reject, but the bridge never submits, issues a general-submit permission or fabricates a receipt. Core must still invoke the dedicated guarded submit adapter, which revalidates the real review.

General v2 authentication/CAPTCHA/device routing returns an explicit adapter-required error; its typed extension interfaces are not successful implementations. Core can request information/helper/declared-review decisions around v2 tools, but cannot use this transport to bypass missing portal safeguards.

## Results, receipts and status back to WhatsApp

POST /notifications queues notification-only progress/result/status/error deliveries. These use the same lease/ACK consumer API but have requires_response=false, never pause browser actions and complete after the consumer ACK. A result/status notification must reference the actual observed v1 receipt; status is read from that adapter. Generic v2 contexts without a reviewed receipt/status adapter reject result/status claims rather than fabricating them. The synthetic_runtime flag remains explicit in every delivery.

Core can download the approved v1 receipt PDF through authenticated GET /integration/v1/sessions/{id}/receipt (BrowserClient.receipt), fetch prepared artifacts with its service credential and upload those bytes through its own messaging provider. Do not send citizens service-key-protected API URLs or embed INTERNAL_KEY in messages. Delivery ACK records provider acceptance as reported by the consumer; actual delivery/read receipts remain the provider/core responsibility. Core must deduplicate notification_id/delivery_id and attach only the correct recipient's verified artifacts.

## Durability, privacy and recovery

Requests, non-secret replies, delivery payloads (including temporary assistance paths), provider references and processed-result metadata are encrypted. Audit events contain IDs/kinds, not answers or tokens. Reply ledgers distinguish pending/processing/completed/failed/cancelled/expired/needs_reconciliation. Delivery leases/ACKs and response IDs survive service restart. No arbitrary callback destination is accepted; core pulls deliveries, avoiding public callback URL/SSRF configuration.

A secret-response timeout is not automatically retried. POST /interrupts/{id}/reconcile checks the actual adapter page state; either completion is observed or a fresh request is required. There is no persisted secret to replay. An old browser generation never becomes a new authenticated session. Cancel affects pending requests/deliveries and the linked human task. Closing/deleting a browser context purges its conversation data; expired terminal requests/deliveries are cleaned on a short TTL-based schedule. Uncertain work requires explicit reconciliation.

The browser service's secret non-retention does not prove that core, n8n execution logs, LangGraph checkpoints, WhatsApp/provider storage or a citizen device retains nothing. Core must configure its own logging/checkpoint/provider policies; use the secure human page where those policies cannot meet the intended OTP handling. Real messaging identity, consent, account setup, provider retries/deduplication and production data policy are external integration requirements.

## Local verification

Run python scripts/verify_conversation.py. It starts isolated services, queues a model-pause-shaped question, consumes/ACKs it through a fake WhatsApp consumer, posts the citizen reply, explicitly confirms the synthetic value and fills the actual general browser field. It also relays a fictional OTP into the actual worker and runs the Node transport example. No external message or AI call is made. Tests cover wrong subject/generation, expiry, delivery lease recovery/ACK replay, duplicate failed OTP answers, encryption, pause enforcement and the fact that approval capture does not submit an application.

The same harness completes an explicitly approved fictional application, downloads its labeled PDF through the authenticated service route and consumes/ACKs result/status notifications bound to its observed receipt. This proves local transport wiring, not a live WhatsApp or real application.

Remaining: connect actual core graph/model, provider webhook verification and messaging, remote modules, real portal-specific auth/review/submit/receipt implementations and deployment. These are named release gates, not hidden fixture fallbacks.
