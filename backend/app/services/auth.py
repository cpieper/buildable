from typing import Any

from itsdangerous import BadData, URLSafeTimedSerializer
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError
from sqlalchemy.orm import Session

from app.models import AppSetting

PASSWORD_HASH_KEY = "auth.password_hash"
REVISION_KEY = "auth.revision"
SESSION_COOKIE_NAME = "what2build_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30

password_hash = PasswordHash.recommended()


class PasswordStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def verify(self, password: str) -> bool:
        setting = self.session.get(AppSetting, PASSWORD_HASH_KEY)
        if setting is None:
            return False
        try:
            return password_hash.verify(password, setting.value)
        except (PwdlibError, ValueError):
            return False

    def revision(self) -> int | None:
        setting = self.session.get(AppSetting, REVISION_KEY)
        if setting is None:
            return None
        try:
            revision = int(setting.value)
        except ValueError:
            return None
        return revision if revision >= 0 else None

    def set_password(self, password: str) -> int:
        current_revision = self.revision()
        revision = (current_revision if current_revision is not None else 0) + 1
        hashed_password = password_hash.hash(password)

        password_setting = self.session.get(AppSetting, PASSWORD_HASH_KEY)
        if password_setting is None:
            password_setting = AppSetting(
                key=PASSWORD_HASH_KEY,
                value=hashed_password,
                secret=True,
            )
            self.session.add(password_setting)
        else:
            password_setting.value = hashed_password
            password_setting.secret = True

        revision_setting = self.session.get(AppSetting, REVISION_KEY)
        if revision_setting is None:
            revision_setting = AppSetting(
                key=REVISION_KEY,
                value=str(revision),
                secret=True,
            )
            self.session.add(revision_setting)
        else:
            revision_setting.value = str(revision)
            revision_setting.secret = True

        self.session.commit()
        return revision


class SessionSigner:
    def __init__(self, secret: str) -> None:
        self.serializer = URLSafeTimedSerializer(secret)

    def create(self, revision: int) -> str:
        return self.serializer.dumps(
            {"authenticated": True, "revision": revision}
        )

    def read(self, token: str) -> int | None:
        try:
            payload: Any = self.serializer.loads(token, max_age=SESSION_MAX_AGE)
        except BadData:
            return None
        if not isinstance(payload, dict) or payload.get("authenticated") is not True:
            return None
        revision = payload.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool):
            return None
        return revision
