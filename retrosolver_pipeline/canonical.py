"""Canonical JSON (RFC 8785 / JCS style) and SHA-256 hashing.

Why JCS: the pack hash must be reproducible by the TypeScript app loader
and the independent validator. JCS sorts object keys and
formats numbers exactly like ECMAScript Number.prototype.toString, so
Python and JavaScript produce byte-identical canonical text.
"""
import decimal
import hashlib
import json
import math


def _es_number(x):
    """Format a number the way ECMAScript Number::toString does."""
    if isinstance(x, bool):
        raise TypeError("bool is not a number here")
    if isinstance(x, int):
        if abs(x) > 2 ** 53:
            raise ValueError("integer outside IEEE-754 safe range: %r" % x)
        x = float(x)
    if not math.isfinite(x):
        raise ValueError("non-finite number cannot be canonicalized: %r" % x)
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    # repr() gives the shortest round-trip decimal digits (same digits ES uses).
    d = decimal.Decimal(repr(abs(x)))
    _, digits, exp = d.as_tuple()
    digits = list(digits)
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exp += 1
    s = "".join(str(c) for c in digits)
    k = len(s)
    n = k + exp  # value = 0.s * 10^n
    if k <= n <= 21:
        out = s + "0" * (n - k)
    elif 0 < n <= 21:
        out = s[:n] + "." + s[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * (-n) + s
    else:
        e = n - 1
        esign = "+" if e >= 0 else "-"
        mant = s if k == 1 else s[0] + "." + s[1:]
        out = mant + "e" + esign + str(abs(e))
    return sign + out


def canonical_json(value):
    """Return the canonical JSON text of value (str)."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _es_number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    if isinstance(value, dict):
        for k in value:
            if not isinstance(k, str):
                raise TypeError("object keys must be strings: %r" % (k,))
        # JCS sorts by UTF-16 code units; identical to Python sort for BMP text.
        keys = sorted(value, key=lambda k: k.encode("utf-16-be"))
        return "{" + ",".join(
            json.dumps(k, ensure_ascii=False) + ":" + canonical_json(value[k]) for k in keys
        ) + "}"
    raise TypeError("unsupported type for canonical JSON: %s" % type(value).__name__)


def sha256_hex(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value):
    return sha256_hex(canonical_json(value))


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
