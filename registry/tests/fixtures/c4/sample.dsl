workspace "Demo" "Made-up example system for tests. Not a real system." {

    !identifiers flat

    properties {
        "tm.version" "1.0"
        "tm.dataclass.PII" "Examples: name. Regulatory: none."
        "structurizr.inspection.model.softwaresystem.documentation" "ignore"
        "structurizr.inspection.model.softwaresystem.decisions" "ignore"
    }

    configuration {
        scope softwaresystem
    }

    model {
        A1 = person "A1 User" "Uses the demo." {
            properties {
                "tm.zone.ENV1" "TB1"
                "tm.was" "E1"
            }
        }

        S1 = softwareSystem "S1 Demo" "The demo system." {
            C1 = container "C1 Web app" "Serves the pages." "Web app" {
                properties {
                    "tm.owner" "Demo team"
                    "tm.was" "P1"
                }
            }
            C2 = container "C2 API" "Answers the web app." "Python" {
                properties {
                    "tm.owner" "Demo team"
                    "tm.was" "P2"
                }
            }
            C3 = container "C3 Database" "Holds the data." "PostgreSQL" "Data store" {
                properties {
                    "tm.owner" "Demo team"
                    "tm.was" "D1"
                    "tm.data.stored" "PII"
                }
            }
        }

        R1 = A1 -> C1 "R1 Browses using" "HTTPS" {
            properties {
                "tm.data.sent" "PII"
                "tm.data.returned" "PII"
                "tm.auth" "Session cookie"
                "tm.was" "F1"
            }
        }
        R2 = C1 -> C2 "R2 Calls" "HTTPS, JSON" {
            properties {
                "tm.data.sent" "PII"
                "tm.data.returned" "PII"
                "tm.auth" "Service token"
                "tm.was" "F2"
            }
        }
        R3 = C2 -> C3 "R3 Reads and writes" "SQL over TLS" {
            properties {
                "tm.data.sent" "PII"
                "tm.data.returned" "PII"
                "tm.auth" "Database user"
                "tm.was" "F3"
            }
        }

        ENV1 = deploymentEnvironment "ENV1 Production" {
            TB1 = deploymentNode "TB1 Internet" "Untrusted public network." "Public internet" "Trust boundary" {
                properties {
                    "tm.enforced_by" "Nothing: an untrusted zone"
                    "tm.was" "TB1"
                }
                N1 = deploymentNode "N1 User device" "The user's own device." "Web browser" {
                    containerInstance C1
                }
            }
            TB2 = deploymentNode "TB2 Cloud" "The demo's cloud network." "Cloud account" "Trust boundary" {
                properties {
                    "tm.enforced_by" "Security groups"
                }
                containerInstance C2
                containerInstance C3
            }
        }
    }

    views {
        systemContext S1 "context" {
            title "System context diagram for S1 Demo"
            include *
            autoLayout lr
        }
        container S1 "containers" {
            title "Container diagram for S1 Demo"
            include *
            autoLayout lr
        }
        deployment * ENV1 "deployment-ENV1" {
            title "Deployment diagram for S1 Demo in ENV1 Production"
            include *
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
