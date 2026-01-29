"""
Development Server Runner
Fixes Windows multiprocessing issues with uvicorn
"""

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting Nigerian Tax Compliance API...")
    print("📍 Server will be available at: http://localhost:8000")
    print("📚 API Documentation: http://localhost:8000/docs")
    print("📖 Alternative Docs: http://localhost:8000/redoc")
    print("\n⏳ Loading application...\n")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],  # Only watch app directory for changes
        log_level="info"
    )