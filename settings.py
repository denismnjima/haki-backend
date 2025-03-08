from pydantic import BaseModel
from dotenv import load_dotenv
import os
load_dotenv()
JWT_SECRET_KEY= os.getenv('JWT_SECRET_KEY')


class Settings(BaseModel):
    authjwt_secret_key:str = JWT_SECRET_KEY