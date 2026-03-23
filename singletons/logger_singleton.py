import logging


class LoggerSingleton:
    # Logging is shared through one configured logger instance.
    _instance = None


    def __new__(cls, *args, **kwargs):
        # Build the singleton once, then keep returning the same object.
        if not cls._instance:
            cls._instance = super(LoggerSingleton, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialize()
        return cls._instance


    def _initialize(self):
        # Use one logger configuration for auth, CRUD, and feed cache events.
        self.logger = logging.getLogger('connectly_logger')
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            # Timestamped logs make the cache demo and test output easier to read.
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)


    def get_logger(self):
        # Reuse the same logger instead of rebuilding handlers in each file.
        return self.logger
