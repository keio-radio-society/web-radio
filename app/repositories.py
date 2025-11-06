from typing import Dict, Optional

from sqlmodel import Session, select

from .models import AppSettings


class SettingsRepository:
    """Data access helper for application settings."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self) -> AppSettings:
        statement = select(AppSettings).where(AppSettings.id == 1)
        result = self.session.exec(statement).first()

        if result is None:
            result = AppSettings(id=1)
            self.session.add(result)
            self.session.commit()
            self.session.refresh(result)

        return result

    def update(self, data: Dict) -> AppSettings:
        settings = self.get()

        for key, value in data.items():
            setattr(settings, key, value)

        self.session.add(settings)
        self.session.commit()
        self.session.refresh(settings)
        return settings

