from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from dotenv import load_dotenv

# Determine the app root directory and find the .env file
APP_ROOT = Path(__file__).parent.parent
PROJECT_ROOT = APP_ROOT.parent

# Try to find .env file in multiple locations, in priority order
ENV_PATHS = [
    APP_ROOT / '.env',         # /aqlon/app/.env
    APP_ROOT.parent / '.env',  # /aqlon/.env
    PROJECT_ROOT / '.env',     # /.env
]

# Find the first .env file that exists
for env_path in ENV_PATHS:
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path))
        print(f"Loaded environment from {env_path}")
        break

class Settings(BaseSettings):
    # App settings
    app_name: str = "aqlon"
    debug: bool = False
    log_level: str = "INFO"
    base_dir: Path = APP_ROOT  # Add base_dir property
    
    # Database settings
    database_url: Optional[str] = None
    postgres_url: Optional[str] = None
    aqlon_db_host: Optional[str] = None
    aqlon_db_port: Optional[str] = None
    aqlon_db_name: Optional[str] = None
    aqlon_db_user: Optional[str] = None
    aqlon_db_password: Optional[str] = None
    
    # OpenAI settings
    openai_api_key: Optional[str] = None
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    def get_effective_database_url(self) -> str:
        """Returns the database URL, using one of the available environment variables."""
        # Return the first non-empty value, in priority order
        if self.database_url:
            return self.database_url
        if self.postgres_url:
            return self.postgres_url
        
        # If individual connection parameters are provided, build a connection string
        if all([self.aqlon_db_host, self.aqlon_db_port, self.aqlon_db_name, 
                self.aqlon_db_user, self.aqlon_db_password]):
            return (f"postgresql://{self.aqlon_db_user}:{self.aqlon_db_password}@"
                    f"{self.aqlon_db_host}:{self.aqlon_db_port}/{self.aqlon_db_name}")
                    
        return None

settings = Settings()

# For debugging, this will show loaded environment during startup
if __name__ == "__main__":
    print(f"App name: {settings.app_name}")
    print(f"Database URL: {settings.get_effective_database_url()}")
    print(f"OpenAI API Key set: {'Yes' if settings.openai_api_key else 'No'}")
