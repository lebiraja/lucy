"""Migration script to add task_chat_messages table."""

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
        # Create task_chat_messages table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_chat_messages (
                id SERIAL PRIMARY KEY,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                sender_id INTEGER REFERENCES agents(id) ON DELETE SET NULL,
                message TEXT NOT NULL,
                message_type VARCHAR(50) DEFAULT 'chat' NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
            )
        """))
        
        # Create index for faster lookups
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_task_chat_messages_task_id 
            ON task_chat_messages(task_id)
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_task_chat_messages_created_at 
            ON task_chat_messages(created_at DESC)
        """))
        
        await conn.commit()
        
    print("✓ Migration completed successfully!")
    print("  - Created task_chat_messages table")
    print("  - Created indexes on task_id and created_at")
    
    await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(run_migration())
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        sys.exit(1)
