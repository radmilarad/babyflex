from sqlalchemy import Column, Integer, String, Float
from .database import Base

class EnergyRecord(Base):
    __tablename__ = 'energy_records'
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(String)
    consumption = Column(Float)
    price = Column(Float)