# 🚀 Quick Start Guide - Nigerian Tax Compliance Platform

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.11+** ([Download](https://www.python.org/downloads/))
- **PostgreSQL 15+** ([Download](https://www.postgresql.org/download/))
- **Redis 7+** ([Download](https://redis.io/download))
- **Node.js 18+** ([Download](https://nodejs.org/))
- **Docker & Docker Compose** (Optional but recommended) ([Download](https://www.docker.com/))
- **Git** ([Download](https://git-scm.com/))

## 📦 Option 1: Quick Setup with Docker (Recommended)

### Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/nigerian-tax-platform.git
cd nigerian-tax-platform
```

### Step 2: Create Environment File

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# Database
DATABASE_URL=postgresql://tax_user:secure_password@db:5432/nigerian_tax_platform
POSTGRES_USER=tax_user
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=nigerian_tax_platform

# Redis
REDIS_URL=redis://redis:6379/0

# JWT
SECRET_KEY=your-super-secret-key-change-this-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# AI APIs
ANTHROPIC_API_KEY=sk-ant-your-api-key-here
OPENAI_API_KEY=sk-your-openai-api-key-here

# AWS S3 (for file storage)
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_BUCKET_NAME=nigerian-tax-docs
AWS_REGION=us-east-1

# Email (SendGrid)
SENDGRID_API_KEY=your-sendgrid-api-key
FROM_EMAIL=noreply@yourdomain.com

# Application
ENVIRONMENT=development
DEBUG=true
ALLOWED_HOSTS=localhost,127.0.0.1
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000

# Sentry (Error Tracking)
SENTRY_DSN=your-sentry-dsn
```

### Step 3: Start Services

```bash
docker-compose up -d
```

This will start:
- PostgreSQL database (port 5432)
- Redis cache (port 6379)
- Backend API (port 8000)
- Frontend app (port 3000)
- Celery worker (background tasks)

### Step 4: Run Database Migrations

```bash
docker-compose exec backend alembic upgrade head
```

### Step 5: Create Test User

```bash
docker-compose exec backend python scripts/create_admin.py
```

### Step 6: Access the Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Admin Panel**: http://localhost:8000/admin

---

## 🛠️ Option 2: Manual Setup (Without Docker)

### Step 1: Set Up PostgreSQL

```bash
# Create database user
sudo -u postgres psql
CREATE USER tax_user WITH PASSWORD 'secure_password';
CREATE DATABASE nigerian_tax_platform OWNER tax_user;
GRANT ALL PRIVILEGES ON DATABASE nigerian_tax_platform TO tax_user;
\q
```

### Step 2: Install Redis

```bash
# On Ubuntu/Debian
sudo apt-get install redis-server
sudo systemctl start redis-server

# On macOS
brew install redis
brew services start redis
```

### Step 3: Set Up Backend

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your settings

# Run database migrations
alembic upgrade head

# Create admin user
python scripts/create_admin.py

# Start backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 4: Set Up Frontend

```bash
# In a new terminal
cd frontend

# Install dependencies
npm install

# Set up environment
cp .env.local.example .env.local
# Edit .env.local

# Start development server
npm run dev
```

### Step 5: Start Celery Worker (Background Tasks)

```bash
# In a new terminal
source venv/bin/activate
celery -A app.celery_app worker --loglevel=info
```

### Step 6: Start Celery Beat (Scheduled Tasks)

```bash
# In a new terminal
source venv/bin/activate
celery -A app.celery_app beat --loglevel=info
```

---

## 📊 Initialize Database with Sample Data

### Option 1: Run SQL Script Directly

```bash
# Connect to PostgreSQL
psql -U tax_user -d nigerian_tax_platform

# Run the schema
\i 02_DATABASE_SCHEMA.sql
```

### Option 2: Use Alembic Migration

```bash
# The schema is already in migrations
alembic upgrade head
```

### Load Sample Data (Optional)

```bash
python scripts/load_sample_data.py
```

---

## 🧪 Verify Installation

### Check Backend Health

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "version": "1.0.0"
}
```

### Check API Documentation

Visit: http://localhost:8000/docs

You should see the Swagger UI with all API endpoints.

### Run Tests

```bash
# Backend tests
pytest

# Frontend tests
cd frontend
npm test
```

---

## 🔑 First Login

**Default Admin Credentials** (created by `create_admin.py`):
- Email: admin@example.com
- Password: Admin@123 (change immediately!)

---

## 📁 Project Structure

```
nigerian-tax-platform/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── businesses.py
│   │   │   ├── customers.py
│   │   │   ├── invoices.py
│   │   │   ├── documents.py
│   │   │   └── vat.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── database.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── business.py
│   │   │   ├── invoice.py
│   │   │   └── document.py
│   │   ├── services/
│   │   │   ├── ai/
│   │   │   │   ├── document_processor.py
│   │   │   │   ├── invoice_intelligence.py
│   │   │   │   └── financial_intelligence.py
│   │   │   ├── email_service.py
│   │   │   └── storage_service.py
│   │   ├── schemas/
│   │   ├── utils/
│   │   └── main.py
│   ├── alembic/
│   │   └── versions/
│   ├── tests/
│   ├── scripts/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── (auth)/
│   │   ├── dashboard/
│   │   ├── invoices/
│   │   ├── documents/
│   │   └── settings/
│   ├── components/
│   ├── lib/
│   ├── public/
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🎯 Next Steps

After successful installation:

1. **Complete Business Profile**
   - Navigate to Settings > Business Profile
   - Add your business details, TIN, VAT number
   - Upload logo

2. **Add Customers**
   - Go to Customers section
   - Add your first customer

3. **Create Your First Invoice**
   - Go to Invoices > Create New
   - Try the natural language input: "Invoice ABC Ltd for 10 laptops at ₦200,000 each"

4. **Upload a Receipt**
   - Go to Documents > Upload
   - Upload a sample receipt
   - Watch AI extract the data automatically

5. **View AI Insights**
   - Check Dashboard for financial insights
   - Review tax optimization recommendations

---

## 🐛 Troubleshooting

### Database Connection Error

```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql

# Test connection
psql -U tax_user -d nigerian_tax_platform -h localhost
```

### Redis Connection Error

```bash
# Check if Redis is running
redis-cli ping
# Should respond: PONG
```

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000
# Kill the process
kill -9 <PID>
```

### AI API Errors

Check your API keys in `.env`:
```bash
echo $ANTHROPIC_API_KEY
echo $OPENAI_API_KEY
```

### Permission Errors

```bash
# Make sure database user has proper permissions
sudo -u postgres psql
GRANT ALL PRIVILEGES ON DATABASE nigerian_tax_platform TO tax_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tax_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO tax_user;
```

---

## 📚 Additional Resources

- [Full Documentation](./docs/README.md)
- [API Reference](http://localhost:8000/docs)
- [Contributing Guide](./CONTRIBUTING.md)
- [Nigerian Tax Guide](./docs/nigerian-tax-guide.md)
- [AI Features Guide](./docs/ai-features.md)

---

## 🆘 Getting Help

- **Issues**: [GitHub Issues](https://github.com/yourusername/nigerian-tax-platform/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/nigerian-tax-platform/discussions)
- **Email**: support@yourdomain.com
- **Slack**: [Join our community](https://slack.yourdomain.com)

---

## 🔐 Security Notes

**IMPORTANT**: Before deploying to production:

1. ✅ Change all default passwords
2. ✅ Generate strong SECRET_KEY
3. ✅ Enable HTTPS/SSL
4. ✅ Set up firewall rules
5. ✅ Configure CORS properly
6. ✅ Enable rate limiting
7. ✅ Set up monitoring & alerts
8. ✅ Regular security audits
9. ✅ Keep dependencies updated
10. ✅ Implement backup strategy

---

## 📈 Performance Tips

- **Database**: Add indexes for frequently queried fields
- **Caching**: Use Redis for session storage
- **CDN**: Use CloudFront/Cloudflare for static assets
- **Background Tasks**: Use Celery for heavy operations
- **Monitoring**: Set up Prometheus + Grafana

---

**You're all set! Start building your AI-powered tax compliance platform! 🚀**