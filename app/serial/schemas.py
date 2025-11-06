from pydantic import BaseModel


class SerialTransmitRequest(BaseModel):
    payload: str

