from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from . import models, database

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.get('/api/data')
def get_data(db: Session = Depends(database.SessionLocal)):
    results = db.query(models.EnergyRecord).all()
    return [{'timestamp': r.timestamp, 'consumption': r.consumption, 'price': r.price} for r in results]