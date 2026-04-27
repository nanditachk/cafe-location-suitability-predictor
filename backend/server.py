from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import joblib
import pandas as pd
import numpy as np
import shap

from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext

# Google Auth
from google.oauth2 import id_token
from google.auth.transport import requests

# Your services
from services.feature_service import get_features
from database import db

import os
from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# APP INIT
# -----------------------------
app = FastAPI(title="Cafe Suitability API")

# -----------------------------
# CONFIG
# -----------------------------
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS"))

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

# -----------------------------
# LOAD MODEL + FEATURES
# -----------------------------
xgb_model = joblib.load("models/xgb_model.pkl")
model_features = joblib.load("models/model_features.pkl")

# -----------------------------
# SHAP INIT (AFTER MODEL LOAD)
# -----------------------------
explainer = shap.TreeExplainer(xgb_model)

# -----------------------------
# PASSWORD HASHING
# -----------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str):
    return pwd_context.verify(password, hashed)

# -----------------------------
# TOKEN FUNCTIONS
# -----------------------------
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# -----------------------------
# SCHEMAS
# -----------------------------
class Location(BaseModel):
    latitude: float
    longitude: float

class UserSignup(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class SaveLocation(BaseModel):
    user_id: str
    latitude: float
    longitude: float
    score: float

# -----------------------------
# ROOT
# -----------------------------
@app.get("/")
def home():
    return {"message": "Cafe Suitability API running 🚀"}

# -----------------------------
# SCORE CONVERSION (1–10)
# -----------------------------
def convert_to_score(pred):
    score = pred * 10
    return round(max(min(score, 10), 1), 2)

# -----------------------------
# PREDICT (WITH SHAP)
# -----------------------------
@app.post("/predict")
async def predict(location: Location):

    try:
        # 1. Get features
        feature_dict = get_features(location.latitude, location.longitude)

        # 2. Convert to DataFrame
        df = pd.DataFrame([feature_dict])

        # 3. Align with model features
        df = df.reindex(columns=model_features, fill_value=0)

        # 4. Predict
        prediction = float(xgb_model.predict(df)[0])
        success_score = convert_to_score(prediction)

        # -----------------------------
        # SHAP EXPLANATION
        # -----------------------------
        shap_values = explainer(df)
        shap_vals = shap_values.values[0]

        feature_names = df.columns.tolist()
        ignore_features = {"rating", "review_count"}

        feature_impact = [
            (name, value)
            for name, value in zip(feature_names, shap_vals)
            if name not in ignore_features
        ]

        # Sort by importance
        feature_impact.sort(key=lambda x: abs(x[1]), reverse=True)

        # Top 3 factors
        top_features = feature_impact[:3]

        explanations = []
        for name, value in top_features:
            direction = "positive" if value > 0 else "negative"
            explanations.append(f"{name} ({direction})")

        # -----------------------------
        # RESPONSE
        # -----------------------------
        return {
            "latitude": float(location.latitude),
            "longitude": float(location.longitude),
            "success_score": success_score,
            "top_factors": explanations
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------
# SIGNUP
# -----------------------------
@app.post("/signup")
async def signup(user: UserSignup):

    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed = hash_password(user.password)

    result = await db.users.insert_one({
        "username": user.username,
        "email": user.email,
        "password": hashed
    })

    return {
        "message": "User created",
        "user_id": str(result.inserted_id)
    }

# -----------------------------
# LOGIN
# -----------------------------
@app.post("/login")
async def login(user: UserLogin):

    db_user = await db.users.find_one({"email": user.email})

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Incorrect password")

    access_token = create_access_token({
        "user_id": str(db_user["_id"]),
        "email": db_user["email"]
    })

    refresh_token = create_refresh_token({
        "user_id": str(db_user["_id"]),
        "email": db_user["email"]
    })

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "username": db_user["username"]
    }

# -----------------------------
# GOOGLE LOGIN
# -----------------------------
@app.post("/google-login")
async def google_login(data: dict):

    token = data.get("token")

    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            GOOGLE_CLIENT_ID
        )

        email = idinfo["email"]
        name = idinfo.get("name", "User")

        user = await db.users.find_one({"email": email})

        if not user:
            result = await db.users.insert_one({
                "username": name,
                "email": email,
                "password": None
            })
            user_id = str(result.inserted_id)
        else:
            user_id = str(user["_id"])

        access_token = create_access_token({
            "user_id": user_id,
            "email": email
        })

        refresh_token = create_refresh_token({
            "user_id": user_id,
            "email": email
        })

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "username": name
        }

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google token")

# -----------------------------
# REFRESH TOKEN
# -----------------------------
@app.post("/refresh-token")
async def refresh_token(req: RefreshRequest):

    try:
        payload = jwt.decode(req.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])

        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token")

        new_access_token = create_access_token({
            "user_id": payload.get("user_id")
        })

        return {"access_token": new_access_token}

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

# -----------------------------
# SAVE LOCATION
# -----------------------------
@app.post("/save-location")
async def save_location(data: SaveLocation):

    await db.locations.insert_one({
        "user_id": data.user_id,
        "latitude": data.latitude,
        "longitude": data.longitude,
        "score": data.score
    })

    return {"message": "Location saved"}