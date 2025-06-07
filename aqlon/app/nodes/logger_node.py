from app.logger import logger

class LoggerNode:
    def __init__(self, log_level: str = "INFO"):
        self.log_level = log_level

    def log(self, message: str, level: str = None):
        if not level:
            level = self.log_level
        logger.log(level.upper(), message)
