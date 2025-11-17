class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class State(metaclass=Singleton):

    def __init__(self):
        self.end_conversation = False
        self.pcm_data = b""
        self.text = ""
        self.last_media_paths = []

    def reset(self):
        self.end_conversation = False
        self.pcm_data = b""
        self.text = ""
        self.last_media_paths = []
