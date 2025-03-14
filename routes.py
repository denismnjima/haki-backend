import os
import uuid
from pathlib import Path
from datetime import timedelta
import magic
from fastapi import Depends, HTTPException, status, APIRouter, UploadFile, File, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func
from sqlalchemy.sql import expression
from sqlalchemy import text
import models
import schemas
import database
from database import get_db
from fastapi_jwt_auth import AuthJWT
from fastapi_jwt_auth.exceptions import AuthJWTException,MissingTokenError
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Optional
from datetime import date
from datetime import date as dt_date, datetime
from b2sdk.v2 import InMemoryAccountInfo, B2Api
import humanize
from typing import List
from google.cloud import storage

router = APIRouter(
    prefix="/api",
    tags=['Authentication', 'Protests', 'Protest Nature', 'Protest Images', 'Direction Mapping']
)


SUPPORTED_FILES = {
    'image/jpeg': 'jpeg',
    'image/png': 'png',
    'image/jpg': 'jpg'
}
key_id = os.getenv('KEY_ID')
application_key = os.getenv('APPLICATION_KEY')
info = InMemoryAccountInfo()

b2_api = B2Api(info)
b2_api.authorize_account("production", key_id,application_key)
bucket = b2_api.get_bucket_by_name('property-app')

@router.post('/upload_image',status_code=status.HTTP_201_CREATED)
async def upload_profile_img(prtest_id: int,description: str,file:UploadFile=File(...),Authorize: AuthJWT=Depends(),db: Session = Depends(get_db)):
    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail= ' No image file uploaded'
        )
    
    file_contents = await file.read()
    size = len(file_contents)

    if size>5242880:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='File should not be larger than 5mb'
        )
    
    file_type = magic.from_buffer(buffer=file_contents, mime=True)

    if file_type not in SUPPORTED_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='File type is not allowed'
        )
    
    try:
        file_name =f"{uuid.uuid4()}.{SUPPORTED_FILES[file_type]}"
        upload_image = bucket.upload_bytes(file_contents,file_name)
        image_url = bucket.get_download_url(file_name)
        #submit image
        new_image = models.ProtestImage(
            image_url=image_url,
            description=description,
            protest_id=prtest_id
        )
        
        db.add(new_image)
        db.commit()

        response = {
            "message": "file successfully",
            "image_url": image_url
        }

        return jsonable_encoder(response)
    
    except Exception as e:

        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail= f"Image upload failed: {e}"
        )


@router.post('/refresh')
def refresh(Authorize: AuthJWT = Depends()):
    """
    Refreshes the access token using a refresh token. Requires a valid refresh token.
    """
    try:
        Authorize.jwt_refresh_token_required()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    current_user = Authorize.get_jwt_subject()
    new_access_token = Authorize.create_access_token(subject=current_user)
    return {"access_token": new_access_token}




@router.post("/create_account",  status_code=status.HTTP_201_CREATED)
def create_user(request: schemas.UserSignUp, db: Session = Depends(get_db)):
    # Check if the email already exists
    existing_user = db.query(models.User).filter(models.User.email == request.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Email already registered")

    hashed_password = generate_password_hash(request.password)
    new_user = models.User(email=request.email, password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.get('/users/me/')
async def read_users_me(Authorize: AuthJWT = Depends(), db: Session = Depends(get_db)):
    Authorize.jwt_required()
    current_user_email = Authorize.get_jwt_subject()
    user = db.query(models.User).filter(models.User.email == current_user_email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/protests", status_code=status.HTTP_201_CREATED, response_model=schemas.Protest)
async def create_protest(protest: schemas.ProtestCreate, db: Session = Depends(get_db), Authorize: AuthJWT = Depends()):
    """
    Registers a new protest in the system.  Requires a valid JWT token.
    """
    try:
        Authorize.jwt_required()
        current_user_email = Authorize.get_jwt_subject()
        user = db.query(models.User).filter(models.User.email == current_user_email).first()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authorized")

    new_protest = models.Protest(
        longitude=protest.longitude,
        latitude=protest.latitude,
        title=protest.title,
        course=protest.course,
        explanation=protest.explanation,
        date=protest.date,
        starting_time=protest.starting_time,
        ending_time=protest.ending_time,
        county=protest.county,
        subcounty=protest.subcounty,
        location_name=protest.location_name,
        created_by=user.id  #  Associate the protest with the logged-in user
    )

    db.add(new_protest)
    db.commit()
    db.refresh(new_protest)
    return new_protest

@router.post("/protest_nature", status_code=status.HTTP_201_CREATED, response_model=schemas.ProtestNature)
async def create_protest_nature(protest_nature: schemas.ProtestNatureCreate, protest_id: int, db: Session = Depends(get_db), Authorize: AuthJWT = Depends()):
    """
    Submits the nature of a protest by a user. Requires a valid JWT token.  Prevents duplicate submissions within 5 minutes.
    """
    try:
        Authorize.jwt_required()
    except MissingTokenError:
        raise HTTPException(status_code=401, detail="Missing JWT token")
    current_user_email = Authorize.get_jwt_subject()
    user = db.query(models.User).filter(models.User.email == current_user_email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Verify that the protest exists
    protest = db.query(models.Protest).filter(models.Protest.id == protest_id).first()
    if protest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Protest not found")

    # Check for recent submissions from this user for this protest
    five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
    recent_submission = db.query(models.ProtestNature).filter(
        models.ProtestNature.user_id == user.id,
        models.ProtestNature.protest_id == protest_id,
        models.ProtestNature.created_at >= five_minutes_ago
    ).first()

    if recent_submission:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,  # Use 429 Too Many Requests
            detail="You can only submit a protest nature once every 5 minutes for a given protest."
        )

    new_protest_nature = models.ProtestNature(
        protest_id=protest_id,
        user_id=user.id,  # Associate the protest nature with the logged-in user
        nature=protest_nature.nature,
        time=protest_nature.time,
        date=protest_nature.date
    )

    db.add(new_protest_nature)
    db.commit()
    db.refresh(new_protest_nature)
    return new_protest_nature


@router.post("/direction_mapping", status_code=status.HTTP_201_CREATED, response_model=schemas.DirectionMapping)
async def create_direction_mapping(direction_mapping: schemas.DirectionMappingCreate, db: Session = Depends(get_db), Authorize: AuthJWT = Depends()):
    Authorize.jwt_required()
    current_user_email = Authorize.get_jwt_subject()
    user = db.query(models.User).filter(models.User.email == current_user_email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_direction_mapping = models.DirectionMapping(
        longitude=direction_mapping.longitude,
        latitude=direction_mapping.latitude,
        user_id=user.id,
        date=direction_mapping.date,
        time=direction_mapping.time,
        protest_id = direction_mapping.protest_id,
    )

    db.add(new_direction_mapping)
    db.commit()
    db.refresh(new_direction_mapping)
    return new_direction_mapping

@router.get("/direction_mapping", response_model=List[schemas.DirectionMapping])
async def get_direction_mappings_by_protest(
    protest_id: int = Query(..., description="The ID of the protest to retrieve direction mappings for."),
    db: Session = Depends(get_db)
):
    """
    Retrieves all direction mappings for a given protest ID.  Requires a valid JWT token.
    """

    direction_mappings = db.query(models.DirectionMapping).filter(models.DirectionMapping.protest_id == protest_id).all()
    return direction_mappings

@router.get("/protests", response_model=None) 
async def get_protest_details(
    date: Optional[date] = Query(None, description="Filter protests by specific date (YYYY-MM-DD). If not provided, returns protests for the current date."),
    db: Session = Depends(get_db),
    Authorize: AuthJWT = Depends()
):

    try:
        Authorize.get_jwt_subject() 
        current_user_email = Authorize.get_jwt_subject()
        user = db.query(models.User).filter(models.User.email == current_user_email).first()

    except:
        user = None 
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authorized")

    # Determine the date to filter by
    filter_date = date if date else dt_date.today()

    # Retrieve the protests for the specified date
    protests = db.query(models.Protest).filter(models.Protest.date == filter_date).all()
    if not protests:
        return []  # Return an empty list if no protests found for the date


    protest_list = []
    for protest in protests:
        # Retrieve protest images, excluding flagged and misleading ones
        images = db.query(models.ProtestImage).filter(
            models.ProtestImage.protest_id == protest.id,
            models.ProtestImage.status.notin_(["flagged", "misleading"])
        ).all()

        # Prepare the image data
        image_data = []
        for image in images:
            image_data.append({
                "id": image.id,
                "image_url": image.image_url,
                "description": image.description,
                "submitted_by": image.submitted_by,
                "status": image.status.value,  # Access ChoiceType value,
                "created_at": image.created_at
            })

        # Get the last 5 protest nature reports for the protest
        last_nature_reports = db.query(models.ProtestNature).filter(
            models.ProtestNature.protest_id == protest.id
        ).order_by(models.ProtestNature.created_at.desc()).limit(5).all()

        # Determine the most prominent nature
        if last_nature_reports:
            nature_counts = {}
            for report in last_nature_reports:
                nature = report.nature.value 
                nature_counts[nature] = nature_counts.get(nature, 0) + 1

            most_prominent_nature = max(nature_counts, key=nature_counts.get)
        else:
            most_prominent_nature = None


        # Construct the protest information
        protest_info = {
            "id": protest.id,
            "longitude": protest.longitude,
            "latitude": protest.latitude,
            "title": protest.title,
            "course": protest.course,
            "explanation": protest.explanation,
            "date": protest.date.isoformat(),  # Convert date to string format
            "starting_time": protest.starting_time.isoformat() if protest.starting_time else None,  # Convert time to string format
            "ending_time": protest.ending_time.isoformat() if protest.ending_time else None, # Convert time to string format
            "county": protest.county,
            "subcounty": protest.subcounty,
            "location_name": protest.location_name,
            "created_at": protest.created_at,
            "images": image_data,
            "nature": most_prominent_nature
        }
        protest_list.append(protest_info)

    return protest_list

@router.get("/protests/{protest_id}", response_model=None)  # Define a custom response model
async def get_protest_by_id(
    protest_id: int,
    db: Session = Depends(get_db),
    Authorize: AuthJWT = Depends()
):
    """
    Retrieves detailed information about a specific protest, including its images (excluding flagged/misleading),
    location, description, creation details, and the most prominent protest nature.  Requires authentication.
    """


    # Retrieve the protest
    protest = db.query(models.Protest).filter(models.Protest.id == protest_id).first()
    if not protest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Protest not found")

    # Retrieve protest images, excluding flagged and misleading ones
    images = db.query(models.ProtestImage).filter(
        models.ProtestImage.protest_id == protest_id,
        models.ProtestImage.status.notin_(["flagged", "misleading"])
    ).all()

    # Prepare the image data
    image_data = []
    for image in images:
        image_data.append({
            "id": image.id,
            "image_url": image.image_url,
            "description": image.description,
            "submitted_by": image.submitted_by,
            "status": image.status.value,  # Access ChoiceType value,
            "created_at": image.created_at
        })

    # Get the last 5 protest nature reports for the protest
    last_nature_reports = db.query(models.ProtestNature).filter(
        models.ProtestNature.protest_id == protest_id
    ).order_by(models.ProtestNature.created_at.desc()).limit(5).all()

    # Determine the most prominent nature
    if last_nature_reports:
        nature_counts = {}
        for report in last_nature_reports:
            nature = report.nature.value # Access ChoiceType value
            nature_counts[nature] = nature_counts.get(nature, 0) + 1

        most_prominent_nature = max(nature_counts, key=nature_counts.get)
    else:
        most_prominent_nature = None

    # Construct the response
    protest_info = {
        "id": protest.id,
        "longitude": protest.longitude,
        "latitude": protest.latitude,
        "title": protest.title,
        "course": protest.course,
        "explanation": protest.explanation,
        "date": protest.date.isoformat(),  # Convert date to string format
        "starting_time": protest.starting_time.isoformat() if protest.starting_time else None,  # Convert time to string format
        "ending_time": protest.ending_time.isoformat() if protest.ending_time else None, # Convert time to string format
        "county": protest.county,
        "subcounty": protest.subcounty,
        "location_name": protest.location_name,
        "created_at": protest.created_at,
        "images": image_data,
        "nature": most_prominent_nature
    }

    return protest_info

@router.get("/protests/search", response_model=None)
async def search_protests(
    q: str = Query(..., description="Search query to filter protests by title, course, explanation, county, or location name."),
    db: Session = Depends(get_db),
):

    

    # Construct the search query using SQLAlchemy's 'text' function for more complex queries
    search_query = f"""
        SELECT *
        FROM protests
        WHERE title ILIKE :query
           OR course ILIKE :query
           OR explanation ILIKE :query
           OR county ILIKE :query
           OR location_name ILIKE :query
    """
    #  ILIKE does a case-insensitive search

    # Execute the query using raw SQL
    result = db.execute(text(search_query), {"query": f"%{q}%"})
    protests = [row for row in result]
    # Ensure to fetch all results into a list

    if not protests:
        return []  # Return an empty list if no protests found

    protest_list = []
    for protest in protests:
        # The 'protest' is a Row object, access columns by index
        protest_id = protest[0]  # Assuming 'id' is the first column

        # Retrieve protest images, excluding flagged and misleading ones
        images = db.query(models.ProtestImage).filter(
            models.ProtestImage.protest_id == protest_id,
            models.ProtestImage.status.notin_(["flagged", "misleading"])
        ).all()

        # Prepare the image data
        image_data = []
        for image in images:
            image_data.append({
                "id": image.id,
                "image_url": image.image_url,
                "description": image.description,
                "submitted_by": image.submitted_by,
                "status": image.status.value,  # Access ChoiceType value
                "created_at": image.created_at
            })

        # Get the last 5 protest nature reports for the protest
        last_nature_reports = db.query(models.ProtestNature).filter(
            models.ProtestNature.protest_id == protest_id
        ).order_by(models.ProtestNature.created_at.desc()).limit(5).all()

        # Determine the most prominent nature
        if last_nature_reports:
            nature_counts = {}
            for report in last_nature_reports:
                nature = report.nature.value  # Access ChoiceType value
                nature_counts[nature] = nature_counts.get(nature, 0) + 1

            most_prominent_nature = max(nature_counts, key=nature_counts.get)
        else:
            most_prominent_nature = None

        # Construct the protest information
        protest_info = {
            "id": protest[0],         # id
            "longitude": protest[1],  # longitude
            "latitude": protest[2],   
            "title": protest[3],      # title
            "course": protest[4],     # course
            "explanation": protest[5],# explanation
            "date": protest[6].isoformat() if isinstance(protest[6], (datetime, date)) else str(protest[6]),
            "starting_time": protest[7].isoformat() if protest[7] else None, # starting_time, if not null
            "ending_time": protest[8].isoformat() if protest[8] else None,   # ending_time, if not null
            "county": protest[9],      # county
            "subcounty": protest[10],   # subcounty
            "location_name": protest[11],# location_name
            "created_at": protest[12], # created_at
            "images": image_data,
            "nature": most_prominent_nature
        }
        protest_list.append(protest_info)

    return protest_list


@router.get("/protest_images")
async def get_protest_images(
    protest_id: int = Query(..., description="The ID of the protest to retrieve images for."),
    db: Session = Depends(get_db)
):
    """
    Retrieves a list of protest images for a given protest ID, filtering by status.
    Returns image details including description, status, and a human-readable "time ago" for creation date.
    """

    allowed_statuses = ["approved", "verified", "not_verified", "flagged"]

    images = db.query(models.ProtestImage).filter(
        models.ProtestImage.protest_id == protest_id,
        models.ProtestImage.status.in_([models.PROTEST_IMAGE_STATUS_CHOICES[i][0] for i in range(len(models.PROTEST_IMAGE_STATUS_CHOICES)) if models.PROTEST_IMAGE_STATUS_CHOICES[i][0] in allowed_statuses])
    ).all()

    if not images:
        return []  

    image_list = []
    for image in images:
        image_list.append({
            "id": image.id,
            "image_url": image.image_url,
            "description": image.description,
            "status": image.status.value,
            "created_at": humanize.naturaltime(image.created_at) 
        })
    return image_list


@router.post('/login')
def login(login:schemas.UserBase,db: Session = Depends(get_db), Authorize: AuthJWT = Depends()):
    user = db.query(models.User).filter(models.User.email == login.email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Invalid Credentials")
    if not check_password_hash(user.password, login.password):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Incorrect password")
    
    access_token = Authorize.create_access_token(subject=user.email)
    refresh_token = Authorize.create_refresh_token(subject=user.email)
    response =  {
             "sucess": True,
             "access_token": access_token,
             "refresh_token":refresh_token,
             "email":user.email,
            }
    return response
