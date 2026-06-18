from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_access_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Cookie'deki token'ı okur, geçerliyse kullanıcıyı döner. Yoksa None."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    user_id = decode_access_token(token)
    if not user_id:
        return None
    return db.query(User).filter(User.id == int(user_id)).first()