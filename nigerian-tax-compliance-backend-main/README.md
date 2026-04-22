## Authentication

### Quick Test

1. Start server: `uvicorn app.main:app --reload`
2. Visit: http://localhost:8000/docs
3. Register: POST `/api/v1/auth/register`
4. Login: POST `/api/v1/auth/login`
5. Copy token and click "Authorize" button
6. Test protected routes

### Default Admin Account

- Email: admin@example.com
- Password: Admin@123

⚠️ **Change this password immediately in production!**


## Quick Setup
```bash
# After migrations
python scripts/create_admin.py
python scripts/seed_test_data.py

# Check everything worked
python scripts/check_db.py
```

### **Create a reset script:**
```python
# scripts/reset_database.py
"""Reset database - DELETE ALL DATA!"""
from app.core.database import Base, engine

print("⚠️  WARNING: This will delete ALL data!")
confirm = input("Type 'DELETE' to confirm: ")

if confirm == "DELETE":
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("✅ Database reset complete!")
else:
    print("❌ Cancelled")
```

---

**Now create these scripts and run them to populate your database! 🚀**