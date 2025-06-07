from loguru import logger

# Centralized logger configuration for the whole app
logger.remove()
logger.add(lambda msg: print(msg, end=""), level="INFO")

# Optionally, you can add file logging, rotation, etc. here
# logger.add("logs/aqlon.log", rotation="1 week", level="DEBUG")
