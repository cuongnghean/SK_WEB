# test_db.py
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

DATABASE_URL = "postgresql://postgres.onmtnvzbeojtxfcpmyxn:Cuong2781997.@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres"

try:
    # Tạo engine kết nối PostgreSQL
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        echo=False
    )

    # Test kết nối
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version();"))
        version = result.scalar()

        print("✅ Kết nối PostgreSQL thành công!")
        print("PostgreSQL Version:")
        print(version)

except SQLAlchemyError as e:
    print("❌ Kết nối thất bại!")
    print("Lỗi:", e)