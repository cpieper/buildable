from pydantic import BaseModel


class LoginRequest(BaseModel):
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class SessionResponse(BaseModel):
    authenticated: bool
