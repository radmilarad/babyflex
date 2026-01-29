# Energy Dashboard (Local Full Stack)

## Setup

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend (React)
```bash
cd frontend
npm install
npm run dev
```

### Database
SQLite DB is stored locally as `backend/local.db`.

```python
from app import database, models

db = database.SessionLocal()
db.add(models.EnergyRecord(timestamp='09:00', consumption=3.1, price=45.2))
db.commit()
db.close()
```

Then open [http://localhost:5173](http://localhost:5173) to view the dashboard.
