🛡️ GARUDA Backend

Guided AI for Real-time Unified Detection & Alerting

The backend/ directory contains the server-side infrastructure for GARUDA. It is responsible for authentication, database interaction, CAPTCHA verification, and providing API endpoints that can later be consumed by the GARUDA tactical dashboard and AI/CV pipeline.

Note: captcha.py is maintained by another team member and is expected to be pushed into the same backend/api/ structure. It is part of the backend API layer but is not authored by the current backend developer.

📁 Backend Structure
backend/
│
├── __init__.py
│
├── api/
│   ├── __init__.py
│   ├── auth.py
│   └── captcha.py
│
└── db/
    ├── __init__.py
    ├── init_db.py
    └── db_operations.py
backend/

The root Python package for the GARUDA backend.

Keeping backend as a package allows the API and database modules to communicate using Python package imports.

🔐 API Layer
backend/api/

Contains the API routes exposed by the GARUDA backend.

auth.py

Handles user authentication.

Current authentication design:

User login
Password verification
JWT-based authentication
Protected API access
CAPTCHA integration
No public user registration

GARUDA is intended for a controlled/government environment, so normal users should not be able to create their own accounts.

Operator accounts are intended to be provisioned by an administrator through the Admin Dashboard.

The authentication flow is conceptually:

User
  │
  ▼
Login Page
  │
  ├── Username
  ├── Password
  └── CAPTCHA
  │
  ▼
FastAPI Authentication API
  │
  ▼
Database
  │
  ├── Verify user
  └── Verify password hash
  │
  ▼
JWT Token
  │
  ▼
Authenticated Dashboard
captcha.py

Contains the CAPTCHA functionality used during authentication.

This module is being developed/maintained by another Team Nexus member and will be integrated into the same API package.

Expected location:

backend/api/captcha.py

This keeps CAPTCHA functionality separate from the main authentication logic while allowing auth.py to use it.

🗄️ Database Layer
backend/db/

Contains database initialization and database-related operations.

The backend currently uses SQLite as the database layer.

The database is intentionally kept separate from the API layer so that API routes do not need to contain raw database setup logic everywhere.

init_db.py

Responsible for initializing the GARUDA database.

Typical responsibilities include:

Creating the SQLite database
Creating required tables
Setting up the initial database structure
Preparing the database before the backend starts

Conceptually:

Application Startup
       │
       ▼
   init_db.py
       │
       ▼
SQLite Database
       │
       ▼
Required Tables
db_operations.py

Contains reusable database operations.

Instead of putting SQL/database logic directly inside API routes, database operations are centralized here.

For example:

auth.py
   │
   │ calls
   ▼
db_operations.py
   │
   │ executes database query
   ▼
SQLite

This separation keeps the codebase easier to maintain and allows additional API modules to reuse the same database functions.

🔗 Package Imports

Because api and db are sibling packages:

backend/
├── api/
└── db/

modules inside api should reference db through the parent backend package.

For example, from:

backend/api/auth.py

to:

backend/db/db_operations.py

the relative import is:

from ..db.db_operations import ...

The two dots mean:

..  → backend/

and then:

db.db_operations

points to:

backend/db/db_operations.py

Using:

from .db.db_operations import ...

would incorrectly look for:

backend/api/db/db_operations.py

which does not exist.

🔑 Authentication Architecture

GARUDA uses a JWT-based authentication architecture.

Why JWT?

JWT allows the backend to authenticate subsequent requests without maintaining a traditional server-side login session for every user.

The basic flow is:

             ┌──────────────┐
             │    Client    │
             │ Login Page   │
             └──────┬───────┘
                    │
             Credentials
                    │
                    ▼
             ┌──────────────┐
             │   FastAPI    │
             │  /auth/...   │
             └──────┬───────┘
                    │
                    ▼
             ┌──────────────┐
             │ Database     │
             │ User Record  │
             └──────┬───────┘
                    │
              Password Check
                    │
                    ▼
             ┌──────────────┐
             │     JWT      │
             │ Access Token │
             └──────┬───────┘
                    │
                    ▼
             Authenticated
                Requests

Passwords should never be stored as plaintext.

Instead:

Password
   │
   ▼
Password Hash
   │
   ▼
Database

During login:

Entered Password
       │
       ▼
Password Hash Verification
       │
       ├── Invalid → Reject Login
       │
       └── Valid
             │
             ▼
        Generate JWT
🧩 Current Backend Responsibilities

At the current stage, the backend is responsible for:

Component	Responsibility
FastAPI	Backend API framework
auth.py	Authentication endpoints and JWT handling
captcha.py	CAPTCHA generation/verification
init_db.py	Database initialization
db_operations.py	Reusable database operations
SQLite	Persistent backend data storage
JWT	Stateless authentication tokens
🔮 Planned Backend Integration

The backend will eventually connect the authentication system to the rest of GARUDA.

The broader architecture is expected to become:

                         GARUDA
                            │
              ┌─────────────┴─────────────┐
              │                           │
         Frontend                    Backend
       Tactical HUD                FastAPI
              │                           │
              │                 ┌─────────┴─────────┐
              │                 │                   │
              │              Auth API          Other APIs
              │                 │                   │
              │                 ▼                   ▼
              │             SQLite            AI/CV Pipeline
              │                                     │
              │                                     ▼
              │                              Detection Events
              │                                     │
              └─────────────────────────────────────┘
                            │
                            ▼
                    Threat Intelligence

Future backend functionality can include APIs for:

Camera information
Detection events
Threat/incident records
Alert status
Evidence records
Audit logs
Dashboard statistics
User management
Admin operations
👤 User & Admin Model

GARUDA distinguishes between normal operators and administrators.

Operator

Operators can:

Log in
Access the tactical dashboard
View camera feeds
View detected threats
View incident information
Perform permitted dashboard actions

Operators cannot create their own accounts.

Administrator

Administrators will be responsible for:

Creating operator accounts
Provisioning users
Deleting users
Managing active sessions
Viewing audit trails
Managing system access

Conceptually:

                 ADMIN
                   │
          Create Operator Account
                   │
                   ▼
              SQLite DB
                   │
                   ▼
              OPERATOR
                   │
                 Login
                   │
                   ▼
            JWT Authentication
                   │
                   ▼
          Tactical Dashboard
🌿 Git Branching

GARUDA follows a feature-branch workflow.

Current repository branches include:

main
│
└── Production-ready stable code

Feature
│
└── Full-stack dashboard integration

Archil_facenet
│
└── Facial Recognition / FaceNet development

Backend development should be performed on the appropriate feature branch rather than directly modifying main.

The goal is to keep main stable while individual components are developed and tested independently.

🚧 Current Development Status
Completed / In Progress

FastAPI backend foundation

Backend package structure

API package

Database package

SQLite integration

Database initialization module

Database operations module

Authentication API foundation

JWT authentication implementation

Password hashing/verification

CAPTCHA module integration point

Admin user-management API

Protected dashboard APIs

Camera/event APIs

Threat/incident APIs

Audit logging API

AI/CV pipeline integration

Frontend ↔ FastAPI integration

🎯 Backend Goal

The backend is being designed as the central control and data layer of GARUDA.

Its job is not to perform the actual computer-vision detection itself. Instead, the backend provides the infrastructure required to:

Authenticate Users
       ↓
Control Access
       ↓
Store System Data
       ↓
Receive AI/CV Events
       ↓
Expose Data through APIs
       ↓
Power the GARUDA Dashboard

This separation allows the AI/ML pipeline, database, frontend dashboard, and authentication system to evolve independently while communicating through well-defined APIs.