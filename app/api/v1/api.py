"""
API Router - Aggregates all endpoint routers
"""
from fastapi import APIRouter
from app.api.v1.endpoints import auth

api_router = APIRouter()

# Include authentication routes
api_router.include_router(auth.router)

# Add more routers here as you build them
# api_router.include_router(invoices.router)
# api_router.include_router(businesses.router)