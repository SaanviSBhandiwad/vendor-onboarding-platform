from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db

DbSession = Annotated[Session, Depends(get_db)]


def get_current_actor() -> str:
    # Placeholder until JWT auth lands (Days 3-4); then this returns the authenticated user.
    return "anonymous"


Actor = Annotated[str, Depends(get_current_actor)]
