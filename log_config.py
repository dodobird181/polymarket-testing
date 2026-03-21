from logging import DEBUG, INFO, WARNING, basicConfig, getLogger

# Configure logger
basicConfig(level=DEBUG, format="%(message)s")

# Silence noisy libraries
getLogger("httpx").setLevel(WARNING)
