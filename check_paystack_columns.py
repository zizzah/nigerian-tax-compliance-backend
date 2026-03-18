from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT enumlabel FROM pg_enum e "
        "JOIN pg_type t ON e.enumtypid = t.oid "
        "WHERE t.typname = 'paymentmethod' "
        "ORDER BY enumsortorder"
    ))
    values = [r[0] for r in result.fetchall()]
    print('PaymentMethod enum values:', values)