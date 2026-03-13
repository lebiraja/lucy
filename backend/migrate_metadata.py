"""Migration script to add task_metadata column to projects table."""

import asyncio
import sys
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Database URL - use environment variable or default Docker service name
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://lucy_user:lucy_pass@db:5432/lucy_db"
)


async def run_migration():
    engine = create_async_engine(DATABASE_URL, echo=True)
    
    async with engine.connect() as conn:
        # Add task_metadata column to projects table
        await conn.execute(text("""
            ALTER TABLE projects 
            ADD COLUMN IF NOT EXISTS task_metadata JSONB
        """))
        
        await conn.commit()
        
    print("✓ Migration completed successfully!")
    print("  - Added task_metadata column to projects table")
    
    await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(run_migration())
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        sys.exit(1)
