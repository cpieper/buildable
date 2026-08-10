from secrets import randbits
from typing import Any

from itsdangerous import BadData, URLSafeTimedSerializer
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError
from sqlalchemy import Integer, and_, case, cast, exists, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.models import AppSetting, utc_now

PASSWORD_HASH_KEY = "auth.password_hash"
REVISION_KEY = "auth.revision"
SESSION_COOKIE_NAME = "what2build_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
SQLITE_MAX_INTEGER = (1 << 63) - 1

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
        return revision if revision > 0 else None

    def set_password(self, password: str) -> int:
        hashed_password = password_hash.hash(password)
        repair_revision = randbits(62) | (1 << 61)
        stored_value = AppSetting.value
        valid_revision = and_(
            stored_value != "",
            stored_value.op("NOT GLOB")("*[^0-9]*"),
            cast(stored_value, Integer) > 0,
            cast(stored_value, Integer) < SQLITE_MAX_INTEGER,
        )
        initial_revision = case(
            (
                exists(
                    select(1)
                    .select_from(AppSetting)
                    .where(AppSetting.key == PASSWORD_HASH_KEY)
                ),
                str(repair_revision),
            ),
            else_="1",
        )
        revision_insert = insert(AppSetting).values(
            key=REVISION_KEY,
            value=initial_revision,
            secret=True,
        )
        revision_value = self.session.execute(
            revision_insert.on_conflict_do_update(
                index_elements=[AppSetting.key],
                set_={
                    "value": case(
                        (
                            valid_revision,
                            cast(stored_value, Integer) + 1,
                        ),
                        else_=str(repair_revision),
                    ),
                    "secret": True,
                    "updated_at": utc_now(),
                },
            )
            .returning(AppSetting.value)
        ).scalar_one()
        revision = int(revision_value)

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
