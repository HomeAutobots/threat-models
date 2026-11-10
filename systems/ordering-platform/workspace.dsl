workspace "Ordering platform" "The guide's reference system: a made-up web and mobile ordering platform. Not a real system." {

    !identifiers flat

    properties {
        "tm.version" "1.0"
        "tm.dataclass.PII" "Examples: name, address, email, phone. Regulatory: GDPR, CCPA."
        "tm.dataclass.Payment tokens" "Examples: provider token, last four digits. Regulatory: PCI DSS scope reduction (SAQ A-EP or similar)."
        "tm.dataclass.Order history" "Examples: items, amounts, timestamps. Regulatory: consumer protection, retention policy."
        "tm.dataclass.Credentials and secrets" "Examples: DB password, provider keys, signing keys. Regulatory: internal policy."
        "tm.dataclass.Audit records" "Examples: actor, action, target, time. Regulatory: SOC 2 evidence."
        "structurizr.inspection.model.softwaresystem.documentation" "ignore"
        "structurizr.inspection.model.softwaresystem.decisions" "ignore"
    }

    configuration {
        scope softwaresystem
    }

    model {
        A1 = person "A1 Customer" "Browses and orders from a browser or the native mobile app. Anonymous until login; self-registers with no identity proofing." {
            properties {
                "tm.zone.ENV1" "outside"
                "tm.was" "E1"
            }
        }
        A2 = person "A2 Store admin" "Employee who handles refunds, order edits and customer lookups. Signs in with SSO and MFA, and reaches the platform only from the admin network." {
            properties {
                "tm.zone.ENV1" "TB5"
                "tm.was" "E2"
            }
        }

        S1 = softwareSystem "S1 Ordering platform" "Takes web and mobile orders and payments; runs on managed Kubernetes in a public cloud." {
            C1 = container "C1 Web front end" "Serves server-rendered pages and static assets behind a CDN." "unknown — ask the architect" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.assumed" "The guide names neither its owner nor its technology."
                    "tm.was" "P1"
                }
            }
            C2 = container "C2 API gateway" "Terminates TLS, rate-limits requests, validates sessions, and takes provider webhooks." "unknown — ask the architect" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.assumed" "The guide names neither its owner nor its technology."
                    "tm.was" "P2"
                }
            }
            C3 = container "C3 Order service" "Core business logic. Owns the orders schema, and reconciles the daily settlement report against orders." "unknown — ask the architect" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.assumed" "The guide names neither its owner nor its technology."
                    "tm.was" "P3"
                }
            }
            C4 = container "C4 Payment adapter" "Wraps the payment providers' APIs and generates PDF receipts." "unknown — ask the architect" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.assumed" "The guide names neither its owner nor its technology."
                    "tm.was" "P4"
                }
            }
            C5 = container "C5 Notification worker" "Consumes order events from the queue and sends email and SMS." "unknown — ask the architect" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.assumed" "The guide names neither its owner nor its technology."
                    "tm.was" "P5"
                }
            }
            C6 = container "C6 Admin console" "Internal web app for refunds, order edits and customer lookup." "unknown — ask the architect" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.assumed" "The guide names neither its owner nor its technology."
                    "tm.was" "P6"
                }
            }
            C7 = container "C7 Support assistant" "LLM-backed chat that answers customers' order questions and drafts refund requests." "unknown — ask the architect" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.assumed" "The guide names neither its owner nor its technology."
                    "tm.was" "P7"
                }
            }
            C8 = container "C8 Admin support agent" "LLM-backed agent that admins reach through C6, with tools on C3." "unknown — ask the architect" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.assumed" "The guide names neither its owner nor its technology."
                    "tm.was" "P8"
                }
            }
            C9 = container "C9 Orders DB" "Holds customer details, order history and payment tokens." "PostgreSQL" "Data store" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.data.stored" "PII, Order history, Payment tokens"
                    "tm.assumed" "The guide names no owner."
                    "tm.was" "D1"
                }
            }
            C10 = container "C10 Object storage" "Holds PDF receipts and order-history export bundles, shared through signed URLs. A receipt shows name, address, items and the card's last four digits." "unknown — ask the platform team" "Data store" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.data.stored" "PII, Order history, Payment tokens"
                    "tm.assumed" "The guide names neither its owner nor its product."
                    "tm.was" "D2"
                }
            }
            C11 = container "C11 Message queue" "Carries order events with at-least-once delivery. Events hold the order ID and contact data." "unknown — ask the platform team" "Data store" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.data.stored" "PII"
                    "tm.assumed" "The guide names neither its owner nor its product."
                    "tm.was" "D3"
                }
            }
            C12 = container "C12 Secrets manager" "Holds database and provider credentials, and issues short-lived tokens." "unknown — ask the platform team" "Data store" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.data.stored" "Credentials and secrets"
                    "tm.assumed" "The guide names neither its owner nor its product."
                    "tm.was" "D4"
                }
            }
            C13 = container "C13 Audit log" "Append-only record of who did what to which order." "unknown — ask the platform team" "Data store" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.data.stored" "Audit records"
                    "tm.assumed" "The guide names neither its owner nor its product."
                    "tm.was" "D5"
                }
            }
            C14 = container "C14 Retrieval index" "Holds help articles, past support tickets written by customers, support macros and refund-policy documents." "unknown — ask the platform team" "Data store" {
                properties {
                    "tm.owner" "unknown — ask the architect"
                    "tm.data.stored" "PII"
                    "tm.assumed" "The guide names neither its owner nor its product, and gives no data class: past tickets written by customers are taken to hold PII."
                    "tm.was" "D6"
                }
            }
        }

        S2 = softwareSystem "S2 Payment provider" "Tokenizes cards and takes card payments; the platform never stores a PAN." "External" {
            properties {
                "tm.was" "E3"
            }
        }
        S3 = softwareSystem "S3 Email / SMS provider" "Sends order emails and text messages, so it receives customer contact data." "External" {
            properties {
                "tm.was" "E4"
            }
        }
        S4 = softwareSystem "S4 Model provider" "Hosted LLM API; receives prompts that may contain order data." "External" {
            properties {
                "tm.was" "E5"
            }
        }
        S5 = softwareSystem "S5 Buy-now-pay-later provider" "Second payment provider beside S2. Its hosted checkout collects credit-decision data from A1 directly." "External" {
            properties {
                "tm.was" "E6"
            }
        }

        R1 = A1 -> C1 "R1 Browses the catalog and places orders using" "HTTPS" {
            properties {
                "tm.data.sent" "PII"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "None until login with email and password, then a session cookie"
                "tm.was" "F1"
            }
        }
        R2 = C1 -> C2 "R2 Sends API requests to" "REST/JSON over HTTPS, TLS terminated at C2" {
            properties {
                "tm.data.sent" "PII"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "The customer's session cookie, validated at C2"
                "tm.was" "F2"
            }
        }
        R3 = C2 -> C3 "R3 Forwards API calls to" "gRPC; TLS unknown — ask the platform team" {
            properties {
                "tm.data.sent" "PII"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "Service JWT presented by C2"
                "tm.assumed" "The guide does not say whether gRPC runs over TLS here."
                "tm.was" "F3"
            }
        }
        R4 = C3 -> C9 "R4 Reads and writes orders and customer details in" "SQL over TLS" {
            properties {
                "tm.data.sent" "PII, Order history"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "C3's database role, with credentials fetched from C12 over R15"
                "tm.was" "F4"
            }
        }
        R5 = C3 -> C11 "R5 Publishes order.created events to" "unknown — ask the platform team" "Async" {
            properties {
                "tm.data.sent" "PII"
                "tm.data.returned" "none"
                "tm.auth" "unknown — ask the platform team"
                "tm.assumed" "The guide gives neither the protocol nor how a publisher is authenticated."
                "tm.was" "F5"
            }
        }
        R6 = C5 -> C11 "R6 Consumes order.created events from" "unknown — ask the platform team" "Async" {
            properties {
                "tm.data.sent" "none"
                "tm.data.returned" "PII"
                "tm.auth" "unknown — ask the platform team"
                "tm.assumed" "The guide gives neither the protocol nor how a consumer is authenticated. Its DFD drew this flow from the queue to the worker; the arrow here starts at the worker, which consumes from the queue, because a path starts at the side that starts the exchange."
                "tm.was" "F6"
            }
        }
        R7 = C5 -> S3 "R7 Sends order emails and text messages through" "HTTPS" {
            properties {
                "tm.data.sent" "PII"
                "tm.data.returned" "none"
                "tm.auth" "Static API key, rotated by hand"
                "tm.was" "F7"
            }
        }
        R8 = C3 -> C4 "R8 Asks for card charges from" "unknown — ask the architect" {
            properties {
                "tm.data.sent" "Payment tokens, Order history"
                "tm.data.returned" "none"
                "tm.auth" "unknown — ask the architect"
                "tm.assumed" "The guide gives neither the protocol nor the authentication. Its level-1 label has this path carry the payment token, but its note on the token read that became R22 says the path then carries only the order reference; both classes are kept until the owner settles it."
                "tm.was" "F8"
            }
        }
        R9 = C4 -> S2 "R9 Charges cards through" "HTTPS with mutual TLS" {
            properties {
                "tm.data.sent" "Payment tokens, Order history"
                "tm.data.returned" "none"
                "tm.auth" "Mutual TLS, with provider credentials fetched from C12 over R16"
                "tm.was" "F9"
            }
        }
        R10 = S2 -> C2 "R10 Posts payment results to" "HTTPS webhook" {
            properties {
                "tm.data.sent" "Payment tokens"
                "tm.data.returned" "none"
                "tm.auth" "unknown — ask the payments lead"
                "tm.assumed" "The guide does not say how C2 authenticates this webhook."
                "tm.was" "F10"
            }
        }
        R11 = C4 -> C10 "R11 Stores PDF receipts in" "unknown — ask the platform team" {
            properties {
                "tm.data.sent" "PII, Order history, Payment tokens"
                "tm.data.returned" "none"
                "tm.auth" "unknown — ask the platform team"
                "tm.assumed" "The guide gives neither the protocol nor the authentication."
                "tm.was" "F11"
            }
        }
        R12 = C3 -> C13 "R12 Appends audit events to" "unknown — ask the platform team" "Async" {
            properties {
                "tm.data.sent" "Audit records"
                "tm.data.returned" "none"
                "tm.auth" "unknown — ask the platform team"
                "tm.assumed" "The guide gives neither the protocol nor the authentication."
                "tm.was" "F12"
            }
        }
        R13 = A2 -> C6 "R13 Issues refunds, edits orders and looks up customers using" "HTTPS" {
            properties {
                "tm.data.sent" "PII, Order history"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "SSO with MFA, only from the admin network through a VPN or zero-trust proxy"
                "tm.was" "F13"
            }
        }
        R14 = C6 -> C3 "R14 Reads and changes any order through" "Internal REST; TLS unknown — ask the platform team" {
            properties {
                "tm.data.sent" "PII, Order history"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "unknown — ask the architect"
                "tm.assumed" "The guide gives neither the authentication nor whether the REST calls use TLS."
                "tm.was" "F14"
            }
        }
        R15 = C3 -> C12 "R15 Fetches its database credentials from" "unknown — ask the platform team" {
            properties {
                "tm.data.sent" "none"
                "tm.data.returned" "Credentials and secrets"
                "tm.auth" "unknown — ask the platform team"
                "tm.assumed" "The guide gives neither the protocol nor how C3 authenticates to C12."
                "tm.was" "F15"
            }
        }
        R16 = C4 -> C12 "R16 Fetches payment provider credentials from" "unknown — ask the platform team" {
            properties {
                "tm.data.sent" "none"
                "tm.data.returned" "Credentials and secrets"
                "tm.auth" "unknown — ask the platform team"
                "tm.assumed" "The guide gives neither the protocol nor how C4 authenticates to C12."
                "tm.was" "F16"
            }
        }
        R17 = C3 -> C10 "R17 Writes order-history export bundles to" "unknown — ask the platform team" {
            properties {
                "tm.data.sent" "PII, Order history"
                "tm.data.returned" "none"
                "tm.auth" "unknown — ask the platform team"
                "tm.assumed" "The guide gives neither the protocol nor the authentication."
                "tm.was" "F17"
            }
        }
        R18 = A1 -> C2 "R18 Chats with the support assistant through" "HTTPS" {
            properties {
                "tm.data.sent" "PII"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "unknown — ask the architect"
                "tm.assumed" "The guide does not say how chat users are authenticated, and does not classify chat text: customers' messages are taken to carry PII."
                "tm.was" "F18"
            }
        }
        R19 = C7 -> C3 "R19 Looks up the chatting customer's orders in" "unknown — ask the architect" {
            properties {
                "tm.data.sent" "none"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "Scoped to the chatting customer; how C3 enforces the scope is unknown — ask the architect"
                "tm.assumed" "The guide gives neither the protocol nor how the scope is enforced."
                "tm.was" "F19"
            }
        }
        R20 = C7 -> S4 "R20 Sends prompts with retrieved order context to" "unknown — ask the architect" {
            properties {
                "tm.data.sent" "PII, Order history"
                "tm.data.returned" "none"
                "tm.auth" "API key"
                "tm.assumed" "The guide gives no protocol."
                "tm.was" "F20"
            }
        }
        R21 = C7 -> C6 "R21 Submits draft refunds for admin approval to" "unknown — ask the architect" {
            properties {
                "tm.data.sent" "Order history"
                "tm.data.returned" "none"
                "tm.auth" "unknown — ask the architect"
                "tm.assumed" "The guide gives neither the protocol nor the identity C7 submits under."
                "tm.was" "F21"
            }
        }
        R22 = C4 -> C9 "R22 Reads payment tokens from" "SQL over TLS" {
            properties {
                "tm.data.sent" "none"
                "tm.data.returned" "Payment tokens"
                "tm.auth" "C4's own database role"
                "tm.was" "F22"
            }
        }
        R23 = C4 -> S5 "R23 Sends charge requests to" "Not mutual TLS; protocol unknown — ask the payments lead" {
            properties {
                "tm.data.sent" "Payment tokens, Order history"
                "tm.data.returned" "none"
                "tm.auth" "A short-lived credential issued from C12"
                "tm.assumed" "The guide says only that this path does not use mutual TLS."
                "tm.was" "F23"
            }
        }
        R24 = S5 -> C2 "R24 Posts payment results to" "HTTPS webhook" {
            properties {
                "tm.data.sent" "Payment tokens"
                "tm.data.returned" "none"
                "tm.auth" "Signed, idempotent webhook ingress: ADR-10, on ADR-07's pattern"
                "tm.assumed" "The guide gives no data class for this webhook; it is taken to carry what R10 carries."
                "tm.was" "F24"
            }
        }
        R25 = C3 -> C4 "R25 Asks for the daily settlement report from" "unknown — ask the architect" {
            properties {
                "tm.data.sent" "none"
                "tm.data.returned" "Order history"
                "tm.auth" "unknown — ask the architect"
                "tm.assumed" "The guide gives neither the protocol nor the authentication."
                "tm.was" "F25"
            }
        }
        R26 = C6 -> C9 "R26 Reads and writes orders directly in" "SQL; TLS unknown — ask the platform team" {
            properties {
                "tm.data.sent" "PII, Order history"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "C6's own database role, with write access; undocumented, found by archaeology"
                "tm.assumed" "The guide does not say whether this undocumented connection uses TLS."
                "tm.was" "F26"
            }
        }
        R27 = C8 -> C3 "R27 Calls get_order, search_customer and issue_refund on" "unknown — ask the architect" {
            properties {
                "tm.data.sent" "PII, Order history"
                "tm.data.returned" "PII, Order history, Payment tokens"
                "tm.auth" "One service identity with C3's admin-level scope"
                "tm.assumed" "The guide gives no protocol."
                "tm.was" "F27"
            }
        }
        R28 = C8 -> S4 "R28 Sends prompts with retrieved context to" "unknown — ask the architect" {
            properties {
                "tm.data.sent" "PII, Order history, Payment tokens"
                "tm.data.returned" "none"
                "tm.auth" "API key"
                "tm.assumed" "The guide gives no protocol."
                "tm.was" "F28"
            }
        }
        R29 = C7 -> C14 "R29 Retrieves help articles, support macros and past tickets from" "unknown — ask the architect" {
            properties {
                "tm.data.sent" "none"
                "tm.data.returned" "PII"
                "tm.auth" "unknown — ask the architect"
                "tm.assumed" "The guide gives neither the protocol nor the authentication. Past tickets are taken to hold PII, as in C14."
                "tm.was" "F29"
            }
        }
        R30 = C8 -> C14 "R30 Retrieves support macros and refund-policy documents from" "unknown — ask the architect" {
            properties {
                "tm.data.sent" "none"
                "tm.data.returned" "none"
                "tm.auth" "unknown — ask the architect"
                "tm.assumed" "The guide gives neither the protocol nor the authentication."
                "tm.was" "F30"
            }
        }
        R31 = C2 -> C7 "R31 Forwards chat messages to" "unknown — ask the architect" {
            properties {
                "tm.data.sent" "PII"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "unknown — ask the architect"
                "tm.assumed" "The guide routes chat through C2 but gives neither the protocol nor the authentication of this hop."
                "tm.was" "F18"
            }
        }
        R32 = C4 -> S5 "R32 Pulls the daily settlement report from" "unknown — ask the payments lead" {
            properties {
                "tm.data.sent" "none"
                "tm.data.returned" "Order history"
                "tm.auth" "The short-lived credential that R23 uses"
                "tm.assumed" "The guide routes the settlement pull through C4 but gives no protocol."
                "tm.was" "F25"
            }
        }
        R33 = C6 -> C8 "R33 Passes admin requests to" "unknown — ask the architect" {
            properties {
                "tm.data.sent" "PII, Order history"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "unknown — ask the architect"
                "tm.assumed" "The guide says admins reach C8 through C6 but draws no flow: the protocol, authentication and data are not given."
            }
        }
        R34 = A1 -> C10 "R34 Downloads receipts and export bundles from" "Signed URL; TLS unknown — ask the platform team" {
            properties {
                "tm.data.sent" "none"
                "tm.data.returned" "PII, Order history, Payment tokens"
                "tm.auth" "Signed URL only, with no session"
                "tm.assumed" "The guide says bundles are downloaded over the receipt flow and receipts use signed URLs, but draws no path from the customer: whether downloads reach C10 directly or through the CDN is not given."
                "tm.was" "F11"
            }
        }

        ENV1 = deploymentEnvironment "ENV1 Production" {
            TB1 = deploymentNode "TB1 Edge" "Internet-facing zone for the web front end and the API gateway." "Public cloud edge behind a CDN and WAF" "Trust boundary" {
                properties {
                    "tm.enforced_by" "CDN and WAF; TLS termination at C2"
                    "tm.was" "TB1"
                }
                I1 = infrastructureNode "I1 CDN and WAF" "Serves static assets and filters internet traffic before it reaches C1 and C2." "unknown — ask the platform team" {
                    properties {
                        "tm.assumed" "The guide names a CDN and WAF but not the product."
                    }
                }
                containerInstance C1
                containerInstance C2
            }
            TB2 = deploymentNode "TB2 Kubernetes cluster" "Runs the platform's services and its message queue." "Managed Kubernetes in a public cloud" "Trust boundary" {
                properties {
                    "tm.enforced_by" "Network policy; only C2 may call C3; service JWTs"
                    "tm.was" "TB2"
                }
                containerInstance C3
                containerInstance C4
                containerInstance C5
                containerInstance C6
                containerInstance C7
                containerInstance C8
                containerInstance C11
            }
            TB3 = deploymentNode "TB3 Data tier" "Holds the platform's data stores." "Private subnets in a public cloud" "Trust boundary" {
                properties {
                    "tm.enforced_by" "Private subnets; credentials from C12; TLS to C9"
                    "tm.was" "TB3"
                }
                containerInstance C9
                containerInstance C10
                containerInstance C12
                containerInstance C13
                containerInstance C14
            }
            TB4 = deploymentNode "TB4 Third parties" "Payment and messaging providers that the cluster calls out to." "Hosted provider APIs" "Trust boundary" {
                properties {
                    "tm.enforced_by" "Egress allow-list; mutual TLS to S2; API key to S3; a short-lived credential from C12 to S5"
                    "tm.was" "TB4"
                }
                softwareSystemInstance S2
                softwareSystemInstance S3
                softwareSystemInstance S5
            }
            TB5 = deploymentNode "TB5 Admin network" "The network store admins work from, and the only place C6 is reachable from." "unknown — ask the platform team" "Trust boundary" {
                properties {
                    "tm.enforced_by" "SSO with MFA; VPN or zero-trust proxy; separate ingress for C6"
                    "tm.assumed" "The guide does not say what kind of network the admin network is."
                    "tm.was" "TB5"
                }
                I2 = infrastructureNode "I2 VPN or zero-trust proxy" "Admits store admins from the admin network to C6's separate ingress." "unknown — ask the platform team" {
                    properties {
                        "tm.assumed" "The guide names a VPN or zero-trust proxy without saying which."
                    }
                }
            }
            TB6 = deploymentNode "TB6 Model provider" "The hosted LLM API that the support assistant and the admin support agent call out to." "Hosted LLM API" "Trust boundary" {
                properties {
                    "tm.enforced_by" "Egress allow-list; provider data-retention terms; no PII in prompts beyond the current order"
                    "tm.was" "TB6"
                }
                softwareSystemInstance S4
            }
        }
    }

    views {
        systemContext S1 "context" {
            title "System context diagram for S1 Ordering platform"
            include *
            autoLayout lr
        }
        container S1 "containers" {
            title "Container diagram for S1 Ordering platform"
            include *
            autoLayout lr
        }
        deployment * ENV1 "deployment-ENV1" {
            title "Deployment diagram for S1 Ordering platform in ENV1 Production, with trust boundaries"
            include *
            autoLayout lr
        }
        dynamic S1 "SEQ1" {
            title "SEQ1 Card payment: a charge and its webhook result"
            R8
            R22
            R9
            R10
            R3
            R4
            autoLayout lr
        }
        styles {
            element "Person" {
                shape Person
            }
            element "Data store" {
                shape Cylinder
            }
            element "External" {
                background #8c8c8c
                color #ffffff
            }
            element "Trust boundary" {
                border Dashed
                stroke #c0392b
                strokeWidth 5
            }
            element "Group" {
                border Dashed
                stroke #c0392b
                strokeWidth 5
            }
            relationship "Async" {
                style Dashed
            }
        }
    }
}
