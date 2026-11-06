"""Naming-pass name forms, shared by plainnames.py, prready.py and naming/names.py.

A key is the plain name a symbol has in the tree: func_/data_/inline_/Struct_/Enum_/Type_ with its
address, `Owner::unknown_<off>_` for a member, `Function::arg<i>` or `Function::var<i>` for a parameter
or local. final(key, stem) is the name it gets: the stem plus the key's address or member offset.
"""
import re

ADDR_TAIL = r"(?:ov\d{3}_)?(?:jpn_|eur_)?[0-9a-f]{8}"
NAMED = re.compile(rf"[A-Za-z][A-Za-z0-9_]*?_({ADDR_TAIL})(?:_[A-Z]+|_\d+)?")
MEMBER = re.compile(r"([a-z][A-Za-z0-9]*)_([0-9a-f]+)_(?:(\d+)_)?")
DEFAULT = re.compile(rf"(func|data|inline|Struct|Enum|Type)_({ADDR_TAIL})((?:_[A-Z]+|_\d+)?)")
SLOT = re.compile(r"(?:arg|var)\d+")
PASCAL = re.compile(r"[A-Z][A-Za-z0-9]*")
CAMEL = re.compile(r"[a-z][A-Za-z0-9]*")
FUNC_STEM = re.compile(r"[A-Z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*")
DATA_STEM = re.compile(r"g?[A-Z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*")
STEMS = {"func": FUNC_STEM, "data": DATA_STEM, "type": PASCAL}
KINDS = {"func": "func", "inline": "func", "data": "data", "Struct": "type", "Enum": "type", "Type": "type"}
RESERVED = set("""
alignas alignof and asm auto bitand bitor bool break case catch char class compl const const_cast
constexpr continue decltype default delete do double dynamic_cast else enum explicit export extern false
float for friend goto if inline int long mutable namespace new noexcept not nullptr operator or private
protected public register reinterpret_cast return short signed sizeof static static_assert static_cast
struct switch template this throw true try typedef typeid typename union unsigned using virtual void
volatile wchar_t while xor near far min max unknown func data arg var Struct Enum Type
""".split())


def final(key, stem):
    if stem in RESERVED or SLOT.fullmatch(stem):
        raise ValueError(f"{stem!r} is reserved")
    outer, sep, inner = key.partition("::")
    if sep:
        if not CAMEL.fullmatch(stem):
            raise ValueError(f"{stem!r}: members, parameters and locals are camelCase")
        m = MEMBER.fullmatch(inner)
        if m and not SLOT.fullmatch(inner):
            return "member", stem + inner[len(m.group(1)):]
        if SLOT.fullmatch(inner):
            return "local", stem
        raise ValueError(f"{key}: the part after :: must be a plain member, arg<i> or var<i>")
    m = DEFAULT.fullmatch(key)
    if not m:
        raise ValueError(f"{key}: not a plain func_/data_/inline_/Struct_/Enum_/Type_ name")
    kind = KINDS[m.group(1)]
    if not STEMS[kind].fullmatch(stem) or re.search(r"(?:^|_)[0-9a-f]{8}(?:_|$)", stem):
        raise ValueError(f"{stem!r}: PascalCase (a library name may keep its underscores; a global may start with g)")
    return kind, f"{stem}_{m.group(2)}{m.group(3)}"


MANGLED_FREE = re.compile(r"^_Z(\d+)")


def own_ident(name):
    if not name.startswith("_Z"):
        return name
    if name.startswith("_ZN"):
        i, last = (4 if name.startswith("_ZNK") else 3), None
        while i < len(name) and name[i] != "E":
            m = re.match(r"\d+", name[i:])
            if not m:
                return None
            j = i + len(m.group())
            last, i = name[j:j + int(m.group())], j + int(m.group())
        return last
    m = MANGLED_FREE.match(name)
    return name[m.end():m.end() + int(m.group(1))] if m else None


def address_of(name):
    m = NAMED.fullmatch(name)
    return m.group(1) if m else None
