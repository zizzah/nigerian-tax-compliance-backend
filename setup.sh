#!/bin/bash

# ============================================================================
# Nigerian Tax Compliance Backend - Automated Setup Script
# ============================================================================
# This script creates all necessary files and folders for the backend
# ============================================================================

set -e  # Exit on error

echo "🚀 Starting Nigerian Tax Compliance Backend Setup..."
echo ""

# ============================================================================
# Step 1: Create Directory Structure
# ============================================================================
echo "📁 Creating directory structure..."

# Create main directories
mkdir -p app/{api/v1/endpoints,core,models,schemas,services/{ai,email,pdf},utils,tests}
mkdir -p alembic/versions
mkdir -p logs
mkdir -p uploads/{receipts,temp}
mkdir -p scripts

# Create __init__.py files
touch app/__init__.py
touch app/api/__init__.py
touch app/api/v1/__init__.py
touch app/api/v1/endpoints/__init__.py
touch app/core/__init__.py
touch app/models/__init__.py
touch app/schemas/__init__.py
touch app/services/__init__.py
touch app/services/ai/__init__.py
touch app/services/email/__init__.py
touch app/services/pdf/__init__.py
touch app/utils/__init__.py
touch app/tests/__init__.py

echo "✅ Directory structure created"
echo ""

# ============================================================================
# Step 2: Create Core Configuration Files
# ============================================================================
echo "⚙️  Creating core configuration files..."

# Create config.py
cat > app/core/config.py << 'EOF'
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Nigerian Tax Compliance API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    
    # Database
    DATABASE_URL: str
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # AI Services (optional - can be empty for now)
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    
    # File Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    STORAGE_TYPE: str = "local"
    
    # Nigerian Tax
    NIGERIAN_VAT_RATE: float = 7.5
    VAT_REGISTRATION_THRESHOLD: float = 25000000
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
EOF

# Create database.py
cat > app/core/database.py << 'EOF'
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
EOF

# Create security.py
cat > app/core/security.py << 'EOF'
from datetime import datetime, timedelta
from typing import Optional
from jose import jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.JWTError:
        return None
EOF

echo "✅ Core configuration files created"
echo ""

# ============================================================================
# Step 3: Create Models
# ============================================================================
echo "🗄️  Creating database models..."

# Create user model
cat > app/models/user.py << 'EOF'
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<User {self.email}>"
EOF

# Update models __init__.py
cat > app/models/__init__.py << 'EOF'
from app.core.database import Base
from app.models.user import User

# Import other models here as we create them
EOF

echo "✅ Database models created"
echo ""

# ============================================================================
# Step 4: Create Main Application
# ============================================================================
echo "🌐 Creating FastAPI application..."

cat > app/main.py << 'EOF'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "message": "Welcome to Nigerian Tax Compliance API",
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True
    )
EOF

echo "✅ FastAPI application created"
echo ""

# ============================================================================
# Step 5: Create Alembic Configuration
# ============================================================================
echo "🔄 Setting up Alembic for database migrations..."

# Create alembic.ini
cat > alembic.ini << 'EOF'
# A generic, single database configuration.

[alembic]
# path to migration scripts
script_location = alembic

# template used to generate migration file names
# file_template = %%(rev)s_%%(slug)s

# sys.path path, will be prepended to sys.path if present.
prepend_sys_path = .

# timezone to use when rendering the date
# timezone =

# max length of characters to apply to the "slug" field
# truncate_slug_length = 40

# set to 'true' to run the environment during the 'revision' command
# revision_environment = false

# set to 'true' to allow .pyc and .pyo files without a source .py file
# sourceless = false

# version location specification
# version_locations = %(here)s/bar:%(here)s/bat:alembic/versions

# version path separator
version_path_separator = os

# the output encoding used when revision files are written
# output_encoding = utf-8

# IMPORTANT: We're using DATABASE_URL from .env via env.py
# So this line is commented out
# sqlalchemy.url = driver://user:pass@localhost/dbname


[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
EOF

# Create alembic env.py
cat > alembic/env.py << 'EOF'
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
from app.core.config import settings
from app.core.database import Base

# Import all models here
from app.models import User

config = context.config

# Set the database URL from settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
EOF

# Create script.py.mako (template for migrations)
cat > alembic/script.py.mako << 'EOF'
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
EOF

echo "✅ Alembic configuration created"
echo ""

# ============================================================================
# Step 6: Create Test Scripts
# ============================================================================
echo "🧪 Creating test scripts..."

cat > test_setup.py << 'EOF'
"""
Test script to verify database connection and basic setup
"""
from app.core.database import engine, SessionLocal
from app.models import User
from app.core.security import get_password_hash
from sqlalchemy import text

print("🔍 Testing database connection...")
print("")

try:
    # Test connection
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("✅ Database connection successful!")
        print("")
    
    # Test User table
    db = SessionLocal()
    try:
        # Create a test user
        test_user = User(
            email="test@example.com",
            password_hash=get_password_hash("testpassword123"),
            is_active=True
        )
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        
        print(f"✅ Test user created successfully")
        print(f"   - ID: {test_user.id}")
        print(f"   - Email: {test_user.email}")
        print("")
        
        # Query the user
        user = db.query(User).filter(User.email == "test@example.com").first()
        print(f"✅ User retrieved from database")
        print(f"   - Email: {user.email}")
        print(f"   - Active: {user.is_active}")
        print("")
        
        # Clean up
        db.delete(user)
        db.commit()
        print("✅ Test user deleted (cleanup)")
        print("")
        
    finally:
        db.close()
    
    print("=" * 60)
    print("🎉 All tests passed! Your setup is working correctly.")
    print("=" * 60)
    print("")
    print("Next steps:")
    print("1. Run: uvicorn app.main:app --reload")
    print("2. Visit: http://localhost:8000/docs")
    print("3. Start building features!")
    print("")
    
except Exception as e:
    print("❌ Error occurred:")
    print(f"   {e}")
    print("")
    import traceback
    traceback.print_exc()
    print("")
    print("Common issues:")
    print("1. Check your DATABASE_URL in .env file")
    print("2. Ensure PostgreSQL database is accessible")
    print("3. Run: alembic upgrade head (to create tables)")
EOF

# Create .env.example
cat > .env.example << 'EOF'
# ============================================================================
# ENVIRONMENT CONFIGURATION TEMPLATE
# ============================================================================
# Copy this file to .env and fill in your actual values
# ============================================================================

# Database - Replace with your actual PostgreSQL connection string
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Secret Key - Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
SECRET_KEY=your-secret-key-here-generate-a-new-one

# AI API Keys (optional - leave empty if not using AI features yet)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# Application Settings
ENVIRONMENT=development
DEBUG=true
API_V1_PREFIX=/api/v1

# CORS Origins (add your frontend URL)
BACKEND_CORS_ORIGINS=["http://localhost:3000", "http://localhost:8000"]

# JWT Settings
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# File Upload
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE_MB=10
STORAGE_TYPE=local

# Nigerian Tax Settings
NIGERIAN_VAT_RATE=7.5
VAT_REGISTRATION_THRESHOLD=25000000
EOF

# Create .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/
.venv

# Environment
.env
.env.local

# Database
*.db
*.sqlite3

# Uploads
uploads/

# Logs
logs/
*.log

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Alembic
alembic/versions/*.pyc

# Testing
.pytest_cache/
.coverage
htmlcov/

# Distribution
dist/
build/
*.egg-info/
EOF

echo "✅ Test scripts and configuration files created"
echo ""

# ============================================================================
# Step 7: Create Helper Scripts
# ============================================================================
echo "📜 Creating helper scripts..."

cat > scripts/generate_secret_key.py << 'EOF'
"""Generate a secure secret key for JWT tokens"""
import secrets

print("=" * 60)
print("SECRET KEY GENERATOR")
print("=" * 60)
print("")
print("Add this to your .env file:")
print("")
print(f"SECRET_KEY={secrets.token_urlsafe(32)}")
print("")
EOF

cat > scripts/check_db.py << 'EOF'
"""Check database connection"""
from app.core.database import engine
from sqlalchemy import text

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        version = result.fetchone()[0]
        print("✅ Database connection successful!")
        print(f"PostgreSQL version: {version}")
except Exception as e:
    print("❌ Database connection failed!")
    print(f"Error: {e}")
EOF

cat > run_dev.sh << 'EOF'
#!/bin/bash
# Development server runner
echo "🚀 Starting development server..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
EOF

chmod +x run_dev.sh

echo "✅ Helper scripts created"
echo ""

# ============================================================================
# Step 8: Create README
# ============================================================================
echo "📖 Creating README..."

cat > README.md << 'EOF'
# Nigerian Tax Compliance Platform - Backend API

AI-powered tax compliance and invoice management system for Nigerian businesses.

## Features

- 🧾 Invoice generation and management
- 📄 Document upload with AI-powered OCR
- 💰 VAT tracking and compliance
- 📊 Financial analytics and insights
- 🤖 AI-powered automation

## Quick Start

### 1. Setup Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your database URL and secret key
nano .env
```

### 2. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### 3. Setup Database

```bash
# Create first migration
alembic revision --autogenerate -m "Initial migration"

# Apply migration
alembic upgrade head
```

### 4. Test Setup

```bash
python test_setup.py
```

### 5. Run Server

```bash
# Using uvicorn
uvicorn app.main:app --reload

# Or using the helper script
./run_dev.sh
```

### 6. Access API

- API Documentation: http://localhost:8000/docs
- Alternative Docs: http://localhost:8000/redoc
- Health Check: http://localhost:8000/health

## Project Structure

```
app/
├── api/v1/endpoints/    # API endpoints
├── core/                # Configuration, database, security
├── models/              # SQLAlchemy models
├── schemas/             # Pydantic schemas
├── services/            # Business logic
│   ├── ai/             # AI processing services
│   ├── email/          # Email services
│   └── pdf/            # PDF generation
└── utils/              # Helper functions
```

## Development

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

### Testing

```bash
pytest
pytest --cov=app tests/
```

## Environment Variables

See `.env.example` for all available configuration options.

### Required Variables

- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - JWT secret key (generate with scripts/generate_secret_key.py)

### Optional Variables

- `ANTHROPIC_API_KEY` - For Claude AI features
- `OPENAI_API_KEY` - For OpenAI features

## License

Proprietary - All rights reserved
EOF

echo "✅ README created"
echo ""

# ============================================================================
# Final Summary
# ============================================================================
echo "=" * 60
echo "✅ SETUP COMPLETE!"
echo "=" * 60
echo ""
echo "📁 Created:"
echo "   - Project directory structure"
echo "   - Core configuration files"
echo "   - Database models (User)"
echo "   - FastAPI application"
echo "   - Alembic migration setup"
echo "   - Test scripts"
echo "   - Helper scripts"
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. Setup your database:"
echo "   - Get PostgreSQL connection string (Neon, Supabase, etc.)"
echo "   - Copy .env.example to .env"
echo "   - Add your DATABASE_URL to .env"
echo ""
echo "2. Generate secret key:"
echo "   python scripts/generate_secret_key.py"
echo "   (Copy output to .env)"
echo ""
echo "3. Create database tables:"
echo "   alembic revision --autogenerate -m 'Initial migration'"
echo "   alembic upgrade head"
echo ""
echo "4. Test your setup:"
echo "   python test_setup.py"
echo ""
echo "5. Start development server:"
echo "   uvicorn app.main:app --reload"
echo "   or"
echo "   ./run_dev.sh"
echo ""
echo "6. Visit API docs:"
echo "   http://localhost:8000/docs"
echo ""
echo "=" * 60
echo "🎉 Happy coding!"
echo "=" * 60
EOF
