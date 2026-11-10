workspace "Shop" "Made-up example for the C4 model design. Not a real system." {

    !identifiers flat

    properties {
        "tm.version" "1.0"
        "tm.dataclass.PII" "Examples: name, address, phone. Regulatory: GDPR, CCPA."
        "tm.dataclass.Payment token" "Examples: provider token, last four digits. Regulatory: PCI DSS."
        "tm.dataclass.Order history" "Examples: items, amounts, timestamps. Regulatory: consumer protection."
        "structurizr.inspection.model.softwaresystem.documentation" "ignore"
        "structurizr.inspection.model.softwaresystem.decisions" "ignore"
    }

    configuration {
        scope softwaresystem
    }

    model {
        A1 = person "A1 Customer" "Browses the shop and places orders." {
            properties {
                "tm.zone.ENV1" "TB1"
            }
        }
        A2 = person "A2 Store admin" "Looks up orders and issues refunds." {
            properties {
                "tm.zone.ENV1" "TB5"
            }
        }

        S1 = softwareSystem "S1 Shop" "Sells goods online." {
            C1 = container "C1 Web front end" "Single-page app that runs in the customer's browser." "React SPA" {
                properties {
                    "tm.owner" "Web team"
                }
            }
            C2 = container "C2 Order API" "Validates orders, charges cards, and serves the admin screens." "Python, FastAPI" {
                properties {
                    "tm.owner" "Orders team"
                    "tm.zoom" "2, 5: hands payment tokens to the provider; serves customers and admins in one process"
                    "tm.enforced_by.TB6" "Role check middleware; admin session from SSO"
                }
                K1 = component "K1 Checkout handler" "Accepts and validates new orders." "FastAPI router" {
                    properties {
                        "tm.owner" "Orders team"
                    }
                }
                K2 = component "K2 Payment client" "Charges cards with the payment provider." "HTTP client" {
                    properties {
                        "tm.owner" "Orders team"
                    }
                }
                group "TB6 Admin handlers" {
                    K3 = component "K3 Admin handler" "Lists orders and issues refunds." "FastAPI router" {
                        properties {
                            "tm.owner" "Orders team"
                        }
                    }
                }
            }
            C3 = container "C3 Orders DB" "Holds orders and customer details." "PostgreSQL 16" "Data store" {
                properties {
                    "tm.owner" "Orders team"
                    "tm.data.stored" "PII, Order history, Payment token"
                }
            }
        }

        S2 = softwareSystem "S2 Payment provider" "Takes card payments." "External"

        R1 = A1 -> C1 "R1 Places orders using" "HTTPS" {
            properties {
                "tm.data.sent" "PII"
                "tm.data.returned" "Order history"
                "tm.auth" "None until sign-in, then a session cookie"
            }
        }
        R2 = C1 -> K1 "R2 Submits orders to" "HTTPS, JSON" {
            properties {
                "tm.data.sent" "PII, Payment token"
                "tm.data.returned" "Order history"
                "tm.auth" "Session cookie and CSRF token"
            }
        }
        R3 = K1 -> C3 "R3 Reads and writes orders in" "SQL over TLS" {
            properties {
                "tm.data.sent" "PII, Order history, Payment token"
                "tm.data.returned" "Order history"
                "tm.auth" "Database user for the API; unknown — ask platform team"
            }
        }
        R4 = K1 -> K2 "R4 Asks for a charge from" "In-process call" {
            properties {
                "tm.data.sent" "Payment token"
                "tm.data.returned" "none"
                "tm.auth" "None: same process"
            }
        }
        R5 = K2 -> S2 "R5 Charges cards using" "HTTPS, mutual TLS" {
            properties {
                "tm.data.sent" "Payment token"
                "tm.data.returned" "none"
                "tm.auth" "Client certificate and API key"
            }
        }
        R6 = A2 -> K3 "R6 Manages orders using" "HTTPS" {
            properties {
                "tm.data.sent" "none"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "SSO with MFA; admin role"
            }
        }
        R7 = K3 -> C3 "R7 Reads and refunds orders in" "SQL over TLS" {
            properties {
                "tm.data.sent" "Order history"
                "tm.data.returned" "PII, Order history"
                "tm.auth" "Database user for the API; unknown — ask platform team"
            }
        }

        ENV1 = deploymentEnvironment "ENV1 Production" {
            TB1 = deploymentNode "TB1 Internet" "Untrusted public network." "Public internet" "Trust boundary" {
                properties {
                    "tm.enforced_by" "Nothing: an untrusted zone"
                }
                N1 = deploymentNode "N1 Customer browser" "The customer's own device." "Web browser" {
                    containerInstance C1
                }
            }
            TB5 = deploymentNode "TB5 Admin network" "Office network for store staff." "Corporate LAN" "Trust boundary" {
                properties {
                    "tm.enforced_by" "VPN with SSO and MFA"
                }
                I1 = infrastructureNode "I1 VPN gateway" "Lets staff reach the admin handlers." "WireGuard"
            }
            TB2 = deploymentNode "TB2 Shop cloud account" "The shop's own cloud network." "AWS VPC" "Trust boundary" {
                properties {
                    "tm.enforced_by" "Security groups; load balancer with TLS"
                }
                TB3 = deploymentNode "TB3 App subnet" "Runs the API." "Private subnet" "Trust boundary" {
                    properties {
                        "tm.enforced_by" "Security group: only the load balancer on 443"
                    }
                    containerInstance C2
                }
                TB4 = deploymentNode "TB4 Data subnet" "Holds the database." "Private subnet" "Trust boundary" {
                    properties {
                        "tm.enforced_by" "Security group: only the app subnet on 5432"
                    }
                    containerInstance C3
                }
            }
            TB7 = deploymentNode "TB7 Payment provider" "Third-party service." "Vendor SaaS" "Trust boundary" {
                properties {
                    "tm.enforced_by" "The provider's own controls; mutual TLS"
                }
                softwareSystemInstance S2
            }
        }
    }

    views {
        systemContext S1 "context" {
            title "System context diagram for S1 Shop"
            include *
            autoLayout lr
        }
        container S1 "containers" {
            title "Container diagram for S1 Shop"
            include *
            autoLayout lr
        }
        component C2 "components-C2" {
            title "Component diagram for C2 Order API"
            include *
            autoLayout lr
        }
        deployment * ENV1 "deployment-ENV1" {
            title "Deployment diagram for S1 Shop in ENV1 Production, with trust boundaries"
            include *
            autoLayout lr
        }
        dynamic C2 "SEQ1" {
            title "SEQ1 Checkout: an order is placed and paid"
            R1
            R2
            R4
            R5
            R3
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
