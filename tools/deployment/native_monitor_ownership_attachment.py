"""One ownership attachment to the monitor's original captured generation."""
import json

from native_durable_database import unique
from native_ownership_observation import NativeOwnershipObservation
from resource_generations import canonical


class MonitorOwnershipAttachment:
    maximum = 20_000

    def __init__(self, guard, captured, seal):
        self.guard, self.captured, self.seal = guard, captured, seal
        self.observer = None
        self.buffer = b''
        self.poisoned = False

    def feed(self, raw):
        try:
            if self.poisoned or self.observer is not None or type(raw) is not bytes or not raw:
                raise ValueError('Ownership attachment unavailable')
            self.buffer += raw
            if len(self.buffer) > self.maximum:
                raise ValueError('Ownership attachment unavailable')
            if b'\n' not in self.buffer:
                return None
            line, extra = self.buffer.split(b'\n', 1)
            if extra:
                raise ValueError('Ownership attachment unavailable')
            value = json.loads(line, object_pairs_hook=unique)
            if type(value) is not dict or set(value) != {'protocol','action','record'}:
                raise ValueError('Ownership attachment unavailable')
            if type(value['protocol']) is not int or value['protocol'] != 2 or value['action'] != 'attach_ownership':
                raise ValueError('Ownership attachment unavailable')
            if line != canonical(value):
                raise ValueError('Ownership attachment unavailable')
            self.observer = NativeOwnershipObservation(self.guard, self.captured, value['record'], self.seal)
            self.buffer = b''
            return self.observer.check()
        except Exception:
            self.close()
            raise ValueError('Ownership attachment unavailable') from None

    def check(self):
        try:
            if self.poisoned:
                raise ValueError('Ownership attachment lost')
            return self.observer.check() if self.observer is not None else {'current':self.guard.check()}
        except Exception:
            self.close()
            raise ValueError('Ownership attachment lost') from None

    def close(self):
        self.poisoned = True
        if self.observer is not None:
            observer, self.observer = self.observer, None
            observer.close()
