class AlertGate:
    """Repeat low alerts at most every five seconds per resource."""
    def __init__(self):
        self.last = {}

    def due(self, name, percentage, threshold, enabled, now):
        if not enabled or percentage > threshold:
            self.last.pop(name, None)
            return False
        if name not in self.last or now - self.last[name] >= 5:
            self.last[name] = now
            return True
        return False
