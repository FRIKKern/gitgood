"""One private input response after original ownership attachment; no effects."""
import copy
import json
import time


def require(value):
    if not value:
        raise ValueError('Private native input exchange unavailable')


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value);value[key] = item
    return value


class MonitorBusinessInputs:
    maximum = 512

    def __init__(self, attachment, token, ownership):
        self.attachment = attachment
        self.token, self.ownership = copy.deepcopy(token), copy.deepcopy(ownership)
        self.buffer = b'';self.deadline = None;self.used = False;self.poisoned = False

    def _check(self):
        observed = self.attachment.check()
        require(observed['current']['current'] is True)
        require({name: observed['current'][name] for name in self.token} == self.token)
        require(observed['ownership'] == self.ownership)
        return observed

    def feed(self, raw):
        try:
            require(not self.poisoned and not self.used and type(raw) is bytes and raw)
            if self.deadline is None:self.deadline = time.monotonic() + 3
            require(time.monotonic() < self.deadline)
            self.buffer += raw;require(len(self.buffer) <= self.maximum)
            if b'\n' not in self.buffer:return None
            line, extra = self.buffer.split(b'\n', 1);require(not extra)
            value = json.loads(line, object_pairs_hook=unique)
            require(type(value) is dict and set(value) == {'protocol', 'action', 'stage'})
            require(type(value['protocol']) is int and value['protocol'] == 2)
            require(value['action'] == 'private_business_inputs')
            require(type(value['stage']) is str and value['stage'] in {'migrate', 'bootstrap'})
            require(line == json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
            self.used = True
            before = self._check()
            inputs = self.attachment.guard.private_business_inputs(value['stage'])
            require(self._check() == before and time.monotonic() < self.deadline)
            self.buffer = b''
            return {'protocol': 2, 'status': 'private_business_inputs', 'guard': copy.deepcopy(self.token),
                    'ownership': copy.deepcopy(self.ownership), 'inputs': inputs}
        except Exception:
            self.close()
            raise ValueError('Private native input exchange unavailable') from None

    def close(self):
        self.poisoned = True;self.buffer = b''
        self.attachment.close()
