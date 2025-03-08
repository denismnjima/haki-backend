from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import router
app = FastAPI()
from fastapi_jwt_auth import AuthJWT
from settings import Settings

# Allow all CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)
@AuthJWT.load_config
def get_config():
    return Settings()

app.include_router(router)
# app.include_router(messages_router)
