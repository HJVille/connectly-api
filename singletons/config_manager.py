class ConfigManager:
    # Shared runtime settings stay in one place through the singleton instance.
    _instance = None
    DEFAULT_SETTINGS = {
        # Homework 7 and 9 feed requests use this as the fallback page size.
        'DEFAULT_PAGE_SIZE': 20,
        # Homework 9 caching reads this timeout instead of hardcoding it in the view.
        'FEED_CACHE_TIMEOUT': 60,
        'ENABLE_ANALYTICS': True,
        'RATE_LIMIT': 100,
    }


    def __new__(cls, *args, **kwargs):
        # Create the singleton once, then reuse it everywhere else.
        if not cls._instance:
            cls._instance = super(ConfigManager, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialize()
        return cls._instance


    def _initialize(self):
        # Start each process with a fresh copy of the default settings.
        self.settings = self.DEFAULT_SETTINGS.copy()


    def get_setting(self, key):
        # Views and tests read shared configuration values from here.
        return self.settings.get(key)


    def set_setting(self, key, value):
        # Tests can override config values without changing the source defaults.
        self.settings[key] = value


    def reset_settings(self):
        # Reset modified settings so one test run does not affect another.
        self.settings = self.DEFAULT_SETTINGS.copy()
