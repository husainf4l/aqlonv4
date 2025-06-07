"""
Server script to run the AQLON API
"""
import uvicorn
import os
from app.settings import settings

def main():
    """
    Run the AQLON API server
    """
    # Default port to 8000 if not specified in environment
    port = int(os.environ.get("AQLON_API_PORT", 8000))
    
    # Start the server
    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",  # Bind to all interfaces
        port=port,
        reload=settings.debug,  # Auto-reload on code changes in debug mode
        log_level="info"
    )

if __name__ == "__main__":
    main()
