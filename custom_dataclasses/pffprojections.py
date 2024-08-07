class PFFProjections:
    def __init__(self, data):
        for key, value in data.items():
            setattr(self, key, value)

    def __str__(self):
        return f"PFF Projections: {self.__dict__}"
    
    def to_dict(self):
        return {attr: getattr(self, attr) for attr in self.__dict__ if not attr.startswith('_')}
    
    