import asyncio
from core.database import AsyncSessionLocal
from workspaces.models import Workspace
from sqlalchemy import select
import authentication.models

async def run():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Workspace.id, Workspace.name, Workspace.status))
        print(res.fetchall())
        
asyncio.run(run())
