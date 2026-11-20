"""Ed25519 签名/验签（纯 Python，扩展坐标实现）。

基于 Daniel J. Bernstein 的公开参考实现 ed25519.py（public domain）改写：
- 用扩展坐标（X, Y, Z, T）做点运算，避免每步求逆，验签从 ~1.7s 降到几十毫秒
- 只保留签名需要的运算，接口：
    publickey(sk) -> 32B
    signature(msg, sk, pk) -> 64B
    checkvalid(sig, msg, pk) -> bool

用于「一机一码」：程序里只放公钥，私钥只在作者手里。
"""
from __future__ import annotations

import hashlib

b = 256
q = 2 ** 255 - 19
l = 2 ** 252 + 27742317777372353535851937790883648493


def H(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()


def inv(x: int) -> int:
    return pow(x, q - 2, q)


d = (-121665 * inv(121666)) % q
I = pow(2, (q - 1) // 4, q)


def xrecover(y: int) -> int:
    xx = (y * y - 1) * inv(d * y * y + 1)
    x = pow(xx, (q + 3) // 8, q)
    if (x * x - xx) % q != 0:
        x = (x * I) % q
    if x % 2 != 0:
        x = q - x
    return x


By = (4 * inv(5)) % q
Bx = xrecover(By)
# 扩展坐标：[X, Y, Z, T]，x = X/Z, y = Y/Z, T = XY/Z
B = [Bx % q, By % q, 1, (Bx * By) % q]
IDENTITY = [0, 1, 1, 0]


def edwards_add(P: list[int], Q: list[int]) -> list[int]:
    X1, Y1, Z1, T1 = P
    X2, Y2, Z2, T2 = Q
    A = (Y1 - X1) * (Y2 - X2) % q
    Bv = (Y1 + X1) * (Y2 + X2) % q
    C = T1 * 2 * d * T2 % q
    D = Z1 * 2 * Z2 % q
    E = Bv - A
    F = D - C
    G = D + C
    Hh = Bv + A
    return [E * F % q, G * Hh % q, F * G % q, E * Hh % q]


def edwards_double(P: list[int]) -> list[int]:
    X1, Y1, Z1, _T1 = P
    A = X1 * X1 % q
    Bv = Y1 * Y1 % q
    C = 2 * Z1 * Z1 % q
    Hh = A + Bv
    E = Hh - (X1 + Y1) * (X1 + Y1) % q
    G = A - Bv
    F = C + G
    return [E * F % q, G * Hh % q, F * G % q, E * Hh % q]


def scalarmult(P: list[int], e: int) -> list[int]:
    Q = IDENTITY
    while e > 0:
        if e & 1:
            Q = edwards_add(Q, P)
        P = edwards_double(P)
        e >>= 1
    return Q


def encodeint(y: int) -> bytes:
    return int(y).to_bytes(b // 8, "little")


def encodepoint(P: list[int]) -> bytes:
    X, Y, Z, _T = P
    zi = inv(Z)
    x = X * zi % q
    y = Y * zi % q
    return int(y | ((x & 1) << (b - 1))).to_bytes(b // 8, "little")


def bit(h: bytes, i: int) -> int:
    return (h[i // 8] >> (i % 8)) & 1


def publickey(sk: bytes) -> bytes:
    h = H(sk)
    a = 2 ** (b - 2) + sum(2 ** i * bit(h, i) for i in range(3, b - 2))
    return encodepoint(scalarmult(B, a))


def Hint(m: bytes) -> int:
    h = H(m)
    return sum(2 ** i * bit(h, i) for i in range(2 * b))


def signature(m: bytes, sk: bytes, pk: bytes) -> bytes:
    h = H(sk)
    a = 2 ** (b - 2) + sum(2 ** i * bit(h, i) for i in range(3, b - 2))
    r = Hint(bytes(h[i] for i in range(b // 8, b // 4)) + m)
    R = scalarmult(B, r)
    S = (r + Hint(encodepoint(R) + pk + m) * a) % l
    return encodepoint(R) + encodeint(S)


def decodeint(s: bytes) -> int:
    return int.from_bytes(s, "little")


def decodepoint(s: bytes) -> list[int]:
    y = int.from_bytes(s, "little") & ((1 << (b - 1)) - 1)
    sign = s[b // 8 - 1] >> 7
    x = xrecover(y)
    if (x & 1) != sign:
        x = q - x
    P = [x, y, 1, x * y % q]
    if not isoncurve(P):
        raise ValueError("point is not on curve")
    return P


def isoncurve(P: list[int]) -> bool:
    X, Y, Z, T = P
    if Z % q == 0:
        return False
    x = X * inv(Z) % q
    y = Y * inv(Z) % q
    return (-x * x + y * y - 1 - d * x * x * y * y) % q == 0 and (T * Z - X * Y) % q == 0


def checkvalid(s: bytes, m: bytes, pk: bytes) -> bool:
    """验签：通过返回 True，任何异常都返回 False。"""
    try:
        if len(s) != b // 4 or len(pk) != b // 8:
            return False
        A = decodepoint(pk)
        R = decodepoint(s[: b // 8])
        S = decodeint(s[b // 8:])
        if S >= l:
            return False
        h = Hint(encodepoint(R) + pk + m)
        P1 = scalarmult(B, S)
        P2 = edwards_add(R, scalarmult(A, h))
        # 投影坐标可能相差一个缩放因子，用交叉相乘比较
        return ((P1[0] * P2[2] - P2[0] * P1[2]) % q == 0
                and (P1[1] * P2[2] - P2[1] * P1[2]) % q == 0)
    except Exception:
        return False
