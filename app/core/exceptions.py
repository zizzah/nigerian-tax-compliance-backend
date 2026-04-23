"""
PRODUCTION ENHANCEMENT: Comprehensive Error Handling
Location: Create new file app/core/exceptions.py

This adds production-grade error handling for all endpoints
"""
from fastapi import Request, status  # type: ignore
from fastapi.responses import JSONResponse  # type: ignore
from fastapi.exceptions import RequestValidationError  # type: ignore
from starlette.exceptions import HTTPException as StarletteHTTPException  # type: ignore
import logging
import traceback
import sys
from datetime import datetime, timezone
from typing import Any, Dict
from sqlalchemy.exc import IntegrityError, OperationalError, DBAPIError  # type: ignore
import re

logger = logging.getLogger(__name__)


# ============================================================================
# CUSTOM EXCEPTION CLASSES
# ============================================================================

class BaseAPIException(Exception):
    """Base exception for all API exceptions"""
    
    def __init__(
        self,
        message: str,
        error_code: str = None,  # type: ignore
        status_code: int = 500,
        details: Dict[str, Any] = None  # type: ignore
    ):
        self.message = message
        self.error_code = error_code or "internal_error"
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class BusinessLogicException(BaseAPIException):
    """Business logic errors"""
    
    def __init__(self, message: str, error_code: str = None, details: Dict = None):  # type: ignore
        super().__init__(
            message=message,
            error_code=error_code or "business_logic_error",
            status_code=400,
            details=details
        )


class ResourceNotFoundException(BaseAPIException):
    """Resource not found"""
    
    def __init__(self, resource: str, identifier: str = None):  # type: ignore
        message = f"{resource} not found"
        if identifier:
            message += f": {identifier}"
        
        super().__init__(
            message=message,
            error_code="resource_not_found",
            status_code=404,
            details={"resource": resource, "identifier": identifier}
        )


class DuplicateResourceException(BaseAPIException):
    """Duplicate resource"""
    
    def __init__(self, resource: str, field: str = None, value: str = None):  # type: ignore
        message = f"{resource} already exists"
        if field:
            message += f" with {field}"
        if value:
            message += f": {value}"
        
        super().__init__(
            message=message,
            error_code="duplicate_resource",
            status_code=409,
            details={"resource": resource, "field": field, "value": value}
        )


class InsufficientQuotaException(BaseAPIException):
    """Subscription quota exceeded"""
    
    def __init__(self, quota_type: str, limit: int, current: int):
        super().__init__(
            message=f"Subscription quota exceeded for {quota_type}",
            error_code="quota_exceeded",
            status_code=402,  # Payment Required
            details={
                "quota_type": quota_type,
                "limit": limit,
                "current": current,
                "upgrade_required": True
            }
        )


class InvalidStateException(BaseAPIException):
    """Invalid state transition"""
    
    def __init__(self, message: str, current_state: str = None, target_state: str = None):  # type: ignore
        super().__init__(
            message=message,
            error_code="invalid_state",
            status_code=400,
            details={
                "current_state": current_state,
                "target_state": target_state
            }
        )


class ExternalServiceException(BaseAPIException):
    """External service error (AI, payment gateway, etc.)"""
    
    def __init__(self, service: str, message: str):
        super().__init__(
            message=f"{service} service error: {message}",
            error_code="external_service_error",
            status_code=503,
            details={"service": service}
        )


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Handle standard HTTP exceptions
    
    Returns consistent error format across all endpoints
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": "http_error",
                "code": exc.status_code,
                "message": exc.detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "path": str(request.url.path),
                "method": request.method
            }
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle Pydantic validation errors
    
    Transforms validation errors into user-friendly messages
    """
    errors = []
    
    for error in exc.errors():
        # Extract field name
        field_path = ".".join(str(x) for x in error["loc"] if x != "body")
        
        # Map error types to user-friendly messages
        error_type = error["type"]
        error_msg = error["msg"]
        
        # Custom messages for common errors
        if error_type == "value_error.missing":
            error_msg = f"{field_path} is required"
        elif error_type == "type_error.integer":
            error_msg = f"{field_path} must be a number"
        elif error_type == "type_error.float":
            error_msg = f"{field_path} must be a decimal number"
        elif error_type == "value_error.email":
            error_msg = "Invalid email format"
        elif "min_length" in error_type:
            error_msg = f"{field_path} is too short"
        elif "max_length" in error_type:
            error_msg = f"{field_path} is too long"
        
        errors.append({
            "field": field_path or "unknown",
            "message": error_msg,
            "type": error_type,
            "input": error.get("input")
        })
    
    logger.warning(
        f"Validation error on {request.method} {request.url.path}",
        extra={
            "errors": errors,
            "request_id": getattr(request.state, "request_id", None)
        }
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "type": "validation_error",
                "code": 422,
                "message": "Validation failed",
                "errors": errors,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "path": str(request.url.path),
                "method": request.method
            }
        }
    )


async def custom_exception_handler(request: Request, exc: BaseAPIException):
    """
    Handle custom API exceptions
    """
    logger.warning(
        f"{exc.error_code}: {exc.message}",
        extra={
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            "details": exc.details,
            "path": str(request.url.path),
            "request_id": getattr(request.state, "request_id", None)
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": "api_error",
                "code": exc.status_code,
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "path": str(request.url.path),
                "method": request.method
            }
        }
    )

async def general_exception_handler(request: Request, exc: Exception):
    exc_type, exc_value, exc_traceback = sys.exc_info()
    tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    
    logger.error(
        "Unhandled exception: %s",
        str(exc),
        extra={"traceback": tb_str}  # full crash details logged server-side
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": "An unexpected error occurred."  # nothing leaked to client
            }
        }
    )

# ============================================================================
# DATABASE ERROR HANDLING
# ============================================================================



async def database_exception_handler(request: Request, exc: DBAPIError):
    """
    Handle database errors
    
    Converts database-specific errors into user-friendly messages
    """
    error_message = "Database error occurred"
    error_code = "database_error"
    details = {}
    
    if isinstance(exc, IntegrityError):
        # Parse integrity errors
        error_str = str(exc.orig).lower()
        
        if "unique" in error_str or "duplicate" in error_str:
            error_message = "This record already exists"
            error_code = "duplicate_record"
            
            # Try to extract field name
            if "key" in error_str:
                
                match = re.search(r'Key \((.*?)\)', str(exc.orig))
                if match:
                    details["field"] = match.group(1)
        
        elif "foreign key" in error_str:
            error_message = "Referenced record not found"
            error_code = "foreign_key_violation"
        
        elif "not null" in error_str:
            error_message = "Required field is missing"
            error_code = "not_null_violation"
    
    elif isinstance(exc, OperationalError):
        error_message = "Database connection error"
        error_code = "connection_error"
        logger.error(f"Database operational error: {exc}", exc_info=True)
    
    logger.error(
        f"Database error on {request.method} {request.url.path}: {error_message}",
        extra={
            "error_code": error_code,
            "details": details,
            "exception": str(exc),
            "request_id": getattr(request.state, "request_id", None)
        }
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "type": "database_error",
                "code": 500,
                "error_code": error_code,
                "message": error_message,
                "details": details,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "path": str(request.url.path),
                "method": request.method
            }
        }
    )


