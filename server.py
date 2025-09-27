from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "Jobs")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "Jobs-Data")

# CRITICAL CHECK: Ensure the required URI is present
if not MONGO_URI:
    # If the variable wasn't set in the .env file, this error is raised immediately.
    raise EnvironmentError("MONGO_URI environment variable is missing. Please check your .env file or environment setup.")

# --- Lifespan Context Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup (DB connection) and shutdown (DB disconnection) events.
    """
    # STARTUP LOGIC (Before yield)
    print("Starting up application...")
    try:
        # The MONGO_URI variable is used here, having been loaded from .env
        client = AsyncIOMotorClient(MONGO_URI)
        
        # Store the client and database instances in the application state
        app.state.mongodb_client = client
        app.state.mongodb = client[DATABASE_NAME]
        print("Successfully connected to MongoDB.")
        
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        
    yield # Application is ready to receive requests

    # SHUTDOWN LOGIC (After yield)
    print("Shutting down application...")
    if hasattr(app.state, 'mongodb_client'):
        app.state.mongodb_client.close()
        print("MongoDB connection closed.")

# Initialize FastAPI, passing the new lifespan context manager
app = FastAPI(
    title="Job Scraper API",
    description="API to receive job data and store it in MongoDB.",
    version="1.0.0",
    lifespan=lifespan # Use the lifespan context manager
)

# Pydantic model for the incoming job data
class Job(BaseModel):
    """
    Data model for a single job posting. 
    """
    id: Optional[str] = None
    title: str = Field(..., description="The job title.")
    company: str = Field(..., description="The hiring company name.")
    location: str = Field(..., description="The location of the job.")
    salary: Optional[str] = Field(None, description="The salary range (optional).")
    description: Optional[str] = Field(None, description="Full job description (optional).")


# API endpoint to receive and save job data
@app.post("/scrap/data", 
          status_code=201, 
          response_description="Job data saved successfully")
async def create_job(job: Job):
    """
    Receives a Job object and inserts it into the MongoDB 'jobs' collection.
    """
    # Ensure the database object is available before trying to insert
    if not hasattr(app.state, 'mongodb'):
        raise HTTPException(
            status_code=503, 
            detail="Database service unavailable. Failed to connect on startup."
        )

    try:
        # Convert Pydantic model to a dictionary using the modern model_dump() method.
        job_data = job.model_dump(exclude_none=True)

        # Insert the data into the collection, using the COLLECTION_NAME loaded from .env
        collection = app.state.mongodb[COLLECTION_NAME]
        result = await collection.insert_one(job_data)
        
        # Return a success message and the ID of the new document
        return {
            "message": "Job data saved successfully", 
            "id": str(result.inserted_id)
        }
        
    except Exception as e:
        # Log the detailed error for debugging purposes
        print(f"Database insertion error: {str(e)}")
        # Raise a generic 500 internal server error to the client
        raise HTTPException(status_code=500, detail=f"Internal Server Error: Could not save job data.")

# This part is for local testing with Uvicorn.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
